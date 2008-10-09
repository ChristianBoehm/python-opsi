##
# Copyright (c) 2005 Apple Computer, Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
WebDAV resources.
"""

__all__ = [
    "DAVPropertyMixIn",
    "DAVResource",
    "DAVLeafResource",
    "DAVPrincipalResource",
    "AccessDeniedError",
    "isPrincipalResource",
    "TwistedACLInheritable",
    "allACL",
    "readonlyACL",
    "davPrivilegeSet",
    "unauthenticatedPrincipal",
]

import urllib

from zope.interface import implements
from twisted.python import log
from twisted.internet.defer import Deferred, maybeDeferred, succeed
from twisted.internet.defer import waitForDeferred, deferredGenerator
from twisted.internet import reactor
from OPSI.web2 import responsecode
from OPSI.web2.http import HTTPError, RedirectResponse, StatusResponse
from OPSI.web2.http_headers import generateContentType
from OPSI.web2.iweb import IResponse
from OPSI.web2.resource import LeafResource
from OPSI.web2.static import MetaDataMixin, StaticRenderMixin
from OPSI.web2.auth.wrapper import UnauthorizedResponse
from OPSI.web2.dav import davxml
from OPSI.web2.dav.davxml import dav_namespace, lookupElement
from OPSI.web2.dav.davxml import twisted_dav_namespace, twisted_private_namespace
from OPSI.web2.dav.idav import IDAVResource, IDAVPrincipalResource
from OPSI.web2.dav.http import NeedPrivilegesResponse
from OPSI.web2.dav.noneprops import NonePropertyStore
from OPSI.web2.dav.util import unimplemented, parentForURL, joinURL
from OPSI.web2.dav.auth import PrincipalCredentials

class DAVPropertyMixIn (MetaDataMixin):
    """
    Mix-in class which implements the DAV property access API in
    L{IDAVResource}.

    There are three categories of DAV properties, for the purposes of how this
    class manages them.  A X{property} is either a X{live property} or a
    X{dead property}, and live properties are split into two categories:

     1. Dead properties.  There are properties that the server simply stores as
        opaque data.  These are store in the X{dead property store}, which is
        provided by subclasses via the L{deadProperties} method.

     2. Live properties which are always computed.  These properties aren't
        stored anywhere (by this class) but instead are derived from the resource
        state or from data that is persisted elsewhere.  These are listed in the
        L{liveProperties} attribute and are handled explicitly by the
        L{readProperty} method.

     3. Live properties may be acted on specially and are stored in the X{dead
        property store}.  These are not listed in the L{liveProperties} attribute,
        but may be handled specially by the property access methods.  For
        example, L{writeProperty} might validate the data and refuse to write
        data it deems inappropriate for a given property.

    There are two sets of property access methods.  The first group
    (L{hasProperty}, etc.) provides access to all properties.  They
    automatically figure out which category a property falls into and act
    accordingly.

    The second group (L{hasDeadProperty}, etc.) accesses the dead property store
    directly and bypasses any live property logic that exists in the first group
    of methods.  These methods are used by the first group of methods, and there
    are cases where they may be needed by other methods.  I{Accessing dead
    properties directly should be done with caution.}  Bypassing the live
    property logic means that values may not be the correct ones for use in
    DAV requests such as PROPFIND, and may be bypassing security checks.  In
    general, one should never bypass the live property logic as part of a client
    request for property data.

    Properties in the L{twisted_private_namespace} namespace are internal to the
    server and should not be exposed to clients.  They can only be accessed via
    the dead property store.
    """
    # Note:
    #  The DAV:owner and DAV:group live properties are only meaningful if you
    # are using ACL semantics (ie. Unix-like) which use them.  This (generic)
    # class does not.

    liveProperties = (
        (dav_namespace, "resourcetype"              ),
        (dav_namespace, "getetag"                   ),
        (dav_namespace, "getcontenttype"            ),
        (dav_namespace, "getcontentlength"          ),
        (dav_namespace, "getlastmodified"           ),
        (dav_namespace, "creationdate"              ),
        (dav_namespace, "displayname"               ),
        (dav_namespace, "supportedlock"             ),
        (dav_namespace, "supported-report-set"      ), # RFC 3253, section 3.1.5
       #(dav_namespace, "owner"                     ), # RFC 3744, section 5.1
       #(dav_namespace, "group"                     ), # RFC 3744, section 5.2
        (dav_namespace, "supported-privilege-set"   ), # RFC 3744, section 5.3
        (dav_namespace, "current-user-privilege-set"), # RFC 3744, section 5.4
        (dav_namespace, "acl"                       ), # RFC 3744, section 5.5
        (dav_namespace, "acl-restrictions"          ), # RFC 3744, section 5.6
        (dav_namespace, "inherited-acl-set"         ), # RFC 3744, section 5.7
        (dav_namespace, "principal-collection-set"  ), # RFC 3744, section 5.8

        (twisted_dav_namespace, "resource-class"),
    )

    def deadProperties(self):
        """
        Provides internal access to the WebDAV dead property store.  You
        probably shouldn't be calling this directly if you can use the property
        accessors in the L{IDAVResource} API instead.  However, a subclass must
        override this method to provide it's own dead property store.

        This implementation returns an instance of L{NonePropertyStore}, which
        cannot store dead properties.  Subclasses must override this method if
        they wish to store dead properties.

        @return: a dict-like object from which one can read and to which one can
            write dead properties.  Keys are qname tuples (ie. C{(namespace, name)})
            as returned by L{davxml.WebDAVElement.qname()} and values are
            L{davxml.WebDAVElement} instances.
        """
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties

    def hasProperty(self, property, request):
        """
        See L{IDAVResource.hasProperty}.
        """
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname[0] == twisted_private_namespace:
            return succeed(False)

        return succeed(qname in self.liveProperties or self.deadProperties().contains(qname))

    def readProperty(self, property, request):
        """
        See L{IDAVResource.readProperty}.
        """
        def defer():
            if type(property) is tuple:
                qname = property
                sname = "{%s}%s" % property
            else:
                qname = property.qname()
                sname = property.sname()

            namespace, name = qname

            if namespace == dav_namespace:
                if name == "resourcetype":
                    # Allow live property to be overriden by dead property
                    if self.deadProperties().contains(qname):
                        return self.deadProperties().get(qname)
                    if self.isCollection():
                        return davxml.ResourceType.collection
                    return davxml.ResourceType.empty

                if name == "getetag":
                    etag = self.etag()
                    if etag is None:
                        return None
                    return davxml.GETETag(etag.generate())

                if name == "getcontenttype":
                    mimeType = self.contentType()
                    if mimeType is None:
                        return None
                    mimeType.params = None # WebDAV getcontenttype property does not include parameters
                    return davxml.GETContentType(generateContentType(mimeType))

                if name == "getcontentlength":
                    length = self.contentLength()
                    if length is None:
                        # TODO: really we should "render" the resource and 
                        # determine its size from that but for now we just 
                        # return an empty element.
                        return davxml.GETContentLength("")
                    else:
                        return davxml.GETContentLength(str(length))

                if name == "getlastmodified":
                    lastModified = self.lastModified()
                    if lastModified is None:
                        return None
                    return davxml.GETLastModified.fromDate(lastModified)

                if name == "creationdate":
                    creationDate = self.creationDate()
                    if creationDate is None:
                        return None
                    return davxml.CreationDate.fromDate(creationDate)

                if name == "displayname":
                    displayName = self.displayName()
                    if displayName is None:
                        return None
                    return davxml.DisplayName(displayName)

                if name == "supportedlock":
                    return davxml.SupportedLock(
                        davxml.LockEntry(davxml.LockScope.exclusive, davxml.LockType.write),
                        davxml.LockEntry(davxml.LockScope.shared   , davxml.LockType.write),
                    )

                if name == "supported-report-set":
                    supported = [davxml.SupportedReport(report,) for report in self.supportedReports()]
                    return davxml.SupportedReportSet(*supported)

                if name == "supported-privilege-set":
                    return self.supportedPrivileges(request)

                if name == "acl-restrictions":
                    return davxml.ACLRestrictions()

                if name == "inherited-acl-set":
                    return davxml.InheritedACLSet(*self.inheritedACLSet())

                if name == "principal-collection-set":
                    d = self.principalCollections(request)
                    d.addCallback(lambda collections: davxml.PrincipalCollectionSet(*collections))
                    return d

                def ifAllowed(privileges, callback):
                    def onError(failure):
                        failure.trap(AccessDeniedError)
                        
                        raise HTTPError(StatusResponse(
                            responsecode.UNAUTHORIZED,
                            "Access denied while reading property %s." % (sname,)
                        ))

                    d = self.checkPrivileges(request, privileges)
                    d.addCallbacks(lambda _: callback(), onError)
                    return d

                if name == "current-user-privilege-set":
                    def callback():
                        d = self.currentPrivileges(request)
                        d.addCallback(lambda privs: davxml.CurrentUserPrivilegeSet(*privs))
                        return d
                    return ifAllowed((davxml.ReadCurrentUserPrivilegeSet(),), callback)

                if name == "acl":
                    def callback():
                        def gotACL(acl):
                            if acl is None:
                                acl = davxml.ACL()
                            return acl
                        d = self.accessControlList(request)
                        d.addCallback(gotACL)
                        return d
                    return ifAllowed((davxml.ReadACL(),), callback)

            elif namespace == twisted_dav_namespace:
                if name == "resource-class":
                    class ResourceClass (davxml.WebDAVTextElement):
                        namespace = twisted_dav_namespace
                        name = "resource-class"
                        hidden = False
                    return ResourceClass(self.__class__.__name__)

            elif namespace == twisted_private_namespace:
                raise HTTPError(StatusResponse(
                    responsecode.FORBIDDEN,
                    "Properties in the %s namespace are private to the server." % (sname,)
                ))

            return self.deadProperties().get(qname)

        return maybeDeferred(defer)

    def writeProperty(self, property, request):
        """
        See L{IDAVResource.writeProperty}.
        """
        assert (
            isinstance(property, davxml.WebDAVElement),
            "Not a property: %r" % (property,)
        )

        def defer():
            if property.protected:
                raise HTTPError(StatusResponse(
                    responsecode.FORBIDDEN,
                    "Protected property %s may not be set." % (property.sname(),)
                ))

            if property.namespace == twisted_private_namespace:
                raise HTTPError(StatusResponse(
                    responsecode.FORBIDDEN,
                    "Properties in the %s namespace are private to the server." % (property.sname(),)
                ))

            return self.deadProperties().set(property)

        return maybeDeferred(defer)

    def removeProperty(self, property, request):
        """
        See L{IDAVResource.removeProperty}.
        """
        def defer():
            if type(property) is tuple:
                qname = property
                sname = "{%s}%s" % property
            else:
                qname = property.qname()
                sname = property.sname()

            if qname in self.liveProperties:
                raise HTTPError(StatusResponse(
                    responsecode.FORBIDDEN,
                    "Live property %s cannot be deleted." % (sname,)
                ))

            if qname[0] == twisted_private_namespace:
                raise HTTPError(StatusResponse(
                    responsecode.FORBIDDEN,
                    "Properties in the %s namespace are private to the server." % (qname[0],)
                ))

            return self.deadProperties().delete(qname)

        return maybeDeferred(defer)

    def listProperties(self, request):
        """
        See L{IDAVResource.listProperties}.
        """
        # FIXME: A set would be better here, that that's a python 2.4+ feature.
        qnames = list(self.liveProperties)

        for qname in self.deadProperties().list():
            if (qname not in qnames) and (qname[0] != twisted_private_namespace):
                qnames.append(qname)

        return succeed(qnames)

    def listAllprop(self, request):
        """
        Some DAV properties should not be returned to a C{DAV:allprop} query.
        RFC 3253 defines several such properties.  This method computes a subset
        of the property qnames returned by L{listProperties} by filtering out
        elements whose class have the C{.hidden} attribute set to C{True}.
        @return: a list of qnames of properties which are defined and are
            appropriate for use in response to a C{DAV:allprop} query.   
        """
        def doList(qnames):
            result = []

            for qname in qnames:
                try:
                    if not lookupElement(qname).hidden:
                        result.append(qname)
                except KeyError:
                    # Unknown element
                    result.append(qname)

            return result

        d = self.listProperties(request)
        d.addCallback(doList)
        return d

    def hasDeadProperty(self, property):
        """
        Same as L{hasProperty}, but bypasses the live property store and checks
        directly from the dead property store.
        """
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        return self.deadProperties().contains(qname)

    def readDeadProperty(self, property):
        """
        Same as L{readProperty}, but bypasses the live property store and reads
        directly from the dead property store.
        """
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        return self.deadProperties().get(qname)

    def writeDeadProperty(self, property):
        """
        Same as L{writeProperty}, but bypasses the live property store and
        writes directly to the dead property store.
        Note that this should not be used unless you know that you are writing
        to an overrideable live property, as this bypasses the logic which
        protects protected properties.  The result of writing to a
        non-overrideable live property with this method is undefined; the value
        in the dead property store may or may not be ignored when reading the
        property with L{readProperty}.
        """
        self.deadProperties().set(property)

    def removeDeadProperty(self, property):
        """
        Same as L{removeProperty}, but bypasses the live property store and acts
        directly on the dead property store.
        """
        if self.hasDeadProperty(property):
            if type(property) is tuple:
                qname = property
            else:
                qname = property.qname()

            self.deadProperties().delete(qname)

    #
    # Overrides some methods in MetaDataMixin in order to allow DAV properties
    # to override the values of some HTTP metadata.
    #
    def contentType(self):
        if self.hasDeadProperty((davxml.dav_namespace, "getcontenttype")):
            return self.readDeadProperty((davxml.dav_namespace, "getcontenttype")).mimeType()
        else:
            return super(DAVPropertyMixIn, self).contentType()

    def displayName(self):
        if self.hasDeadProperty((davxml.dav_namespace, "displayname")):
            return str(self.readDeadProperty((davxml.dav_namespace, "displayname")))
        else:
            return super(DAVPropertyMixIn, self).displayName()

class DAVResource (DAVPropertyMixIn, StaticRenderMixin):
    implements(IDAVResource)

    ##
    # DAV
    ##

    def davComplianceClasses(self):
        """
        This implementation raises L{NotImplementedError}.
        @return: a sequence of strings denoting WebDAV compliance classes.  For
            example, a DAV level 2 server might return ("1", "2").
        """
        unimplemented(self)

    def isCollection(self):
        """
        See L{IDAVResource.isCollection}.

        This implementation raises L{NotImplementedError}; a subclass must
        override this method.
        """
        unimplemented(self)

    def findChildren(self, depth, request, callback, privileges=None, inherited_aces=None):
        """
        See L{IDAVResource.findChildren}.

        This implementation works for C{depth} values of C{"0"}, C{"1"}, 
        and C{"infinity"}.  As long as C{self.listChildren} is implemented
        """
        assert depth in ("0", "1", "infinity"), "Invalid depth: %s" % (depth,)

        if depth == "0" or not self.isCollection():
            return succeed(None)

        completionDeferred = Deferred()
        basepath = request.urlForResource(self)
        children = list(self.listChildren())

        def checkPrivilegesError(failure):
            failure.trap(AccessDeniedError)
            reactor.callLater(0, getChild)

        def checkPrivileges(child):
            if child is None:
                return None

            if privileges is None:
                return child
   
            d = child.checkPrivileges(request, privileges, inherited_aces=inherited_aces)
            d.addCallback(lambda _: child)
            return d

        def gotChild(child, childpath):
            if child is None:
                callback(None, childpath + "/")
            else:
                if child.isCollection():
                    callback(child, childpath + "/")
                    if depth == "infinity":
                        d = child.findChildren(depth, request, callback, privileges)
                        d.addCallback(lambda x: reactor.callLater(0, getChild))
                        return d
                else:
                    callback(child, childpath)

            reactor.callLater(0, getChild)

        def getChild():
            try:
                childname = children.pop()
            except IndexError:
                completionDeferred.callback(None)
            else:
                childpath = joinURL(basepath, childname)
                d = request.locateChildResource(self, childname)
                d.addCallback(checkPrivileges)
                d.addCallbacks(gotChild, checkPrivilegesError, (childpath,))
                d.addErrback(completionDeferred.errback)

        getChild()

        return completionDeferred

    def supportedReports(self):
        """
        See L{IDAVResource.supportedReports}.
        This implementation lists the three main ACL reports.
        """
        result = []
        result.append(davxml.Report(davxml.ACLPrincipalPropSet(),))
        result.append(davxml.Report(davxml.PrincipalMatch(),))
        result.append(davxml.Report(davxml.PrincipalPropertySearch(),))
        return result

    ##
    # Authentication
    ##

    def authorize(self, request, privileges, recurse=False):
        """
        See L{IDAVResource.authorize}.
        """
        def onError(failure):
            log.err("Invalid authentication details: %s" % (request,))
            raise HTTPError(UnauthorizedResponse(
                request.credentialFactories,
                request.remoteAddr
            ))

        def onAuth(result):
            def onErrors(failure):
                failure.trap(AccessDeniedError)
                
                # If we were unauthorized to start with (no Authorization header from client) then
                # we should return an unauthorized response instead to force the client to login if it can
                if request.user == davxml.Principal(davxml.Unauthenticated()):
                    response = UnauthorizedResponse(request.credentialFactories,
                                                    request.remoteAddr)
                else:
                    response = NeedPrivilegesResponse(request.uri,
                                                      failure.value.errors)
                #
                # We're not adding the headers here because this response
                # class is supposed to be a FORBIDDEN status code and
                # "Authorization will not help" according to RFC2616
                #
                raise HTTPError(response)

            d = self.checkPrivileges(request, privileges, recurse)
            d.addErrback(onErrors)
            return d

        d = maybeDeferred(self.authenticate, request)
        d.addCallbacks(onAuth, onError)

        return d

    def authenticate(self, request):
        def loginSuccess(result):
            request.user = result[1]
            return request.user

        if not (
            hasattr(request, 'portal') and 
            hasattr(request, 'credentialFactories') and
            hasattr(request, 'loginInterfaces')
        ):
            request.user = davxml.Principal(davxml.Unauthenticated())
            return request.user

        authHeader = request.headers.getHeader('authorization')

        if authHeader is not None:
            if authHeader[0] not in request.credentialFactories:
                log.err("Client authentication scheme %s is not provided by server %s"
                        % (authHeader[0], request.credentialFactories.keys()))
                raise HTTPError(responsecode.FORBIDDEN)
            else:
                factory = request.credentialFactories[authHeader[0]]

                creds = factory.decode(authHeader[1], request)

                # Try to match principals in each principal collection on the resource
                def gotDetails(details):
                    principal = IDAVPrincipalResource(details[0])
                    principalURI = details[1]
                    return PrincipalCredentials(principal, principalURI, creds)

                def login(pcreds):
                    d = request.portal.login(pcreds, None, *request.loginInterfaces)
                    d.addCallback(loginSuccess)

                    return d

                d = self.findPrincipalForAuthID(request, creds.username)
                d.addCallback(gotDetails).addCallback(login)

                return d
        else:
            request.user = davxml.Principal(davxml.Unauthenticated())
            return request.user

    ##
    # ACL
    ##

    def currentPrincipal(self, request):
        """
        @param request: the request being processed.
        @return: the current principal, as derived from the given request.
        """
        if hasattr(request, "user"):
            return request.user
        else:
            return unauthenticatedPrincipal

    def principalCollections(self, request):
        """
        See L{IDAVResource.accessControlList}.

        This implementation tries to read the L{davxml.PrincipalCollectionSet}
        from the dead property store of this resource and uses that. If not
        present on this resource, it tries to get it from the parent, unless it
        is the root or has no parent.
        """
        try:
            principalCollections = self.readDeadProperty(davxml.PrincipalCollectionSet).childrenOfType(davxml.HRef)
        except HTTPError, e:
            if e.response.code != responsecode.NOT_FOUND:
                raise

            principalCollections = []

            # Try the parent
            myURL = request.urlForResource(self)
            if myURL != "/":
                parentURL = parentForURL(myURL)

                parent = waitForDeferred(request.locateResource(parentURL))
                yield parent
                parent = parent.getResult()

                if parent:
                    principalCollections = waitForDeferred(parent.principalCollections(request))
                    yield principalCollections
                    principalCollections = principalCollections.getResult()

        yield principalCollections

    principalCollections = deferredGenerator(principalCollections)

    def defaultAccessControlList(self):
        """
        @return: the L{davxml.ACL} element containing the default access control
            list for this resource.
        """
        #
        # The default behaviour is to allow GET access to everything
        # and deny any type of write access (PUT, DELETE, etc.) to
        # everything.
        #
        return readonlyACL

    def setAccessControlList(self, acl):
        """
        See L{IDAVResource.setAccessControlList}.

        This implementation stores the ACL in the private property
        C{(L{twisted_private_namespace}, "acl")}.
        """
        self.writeDeadProperty(acl)

    def mergeAccessControlList(self, new_acl, request):
        """
        Merges the supplied access control list with the one on this resource.
        Merging means change all the non-inherited and non-protected ace's in
        the original, and do not allow the new one to specify an inherited or
        protected access control entry. This is the behaviour required by the
        C{ACL} request. (RFC 3744, section 8.1).
        @param new_acl:  an L{davxml.ACL} element
        @param request: the request being processed.
        @return: a tuple of the C{DAV:error} precondition element if an error
            occurred, C{None} otherwise.

        This implementation stores the ACL in the private property
        """
        # C{(L{twisted_private_namespace}, "acl")}.
        
        # Steps for ACL evaluation:
        #  1. Check that ace's on incoming do not match a protected ace
        #  2. Check that ace's on incoming do not match an inherited ace
        #  3. Check that ace's on incoming all have deny before grant
        #  4. Check that ace's on incoming do not use abstract privilege
        #  5. Check that ace's on incoming are supported (and are not inherited themselves)
        #  6. Check that ace's on incoming have valid principals
        #  7. Copy the original
        #  8. Remove all non-inherited and non-protected - and also inherited
        #  9. Add in ace's from incoming
        # 10. Verify that new acl is not in conflict with itself
        # 11. Update acl on the resource

        old_acl = waitForDeferred(self.accessControlList(request))
        yield old_acl
        old_acl = old_acl.getResult()

        # Check disabled
        if old_acl is None:
            yield None

        # Need to get list of supported privileges
        supported = []
        def addSupportedPrivilege(sp):
            """
            Add the element in any DAV:Privilege to our list
            and recurse into any DAV:SupportedPrivilege's
            """
            for item in sp.children:
                if isinstance(item, davxml.Privilege):
                    supported.append(item.children[0])
                elif isinstance(item, davxml.SupportedPrivilege):
                    addSupportedPrivilege(item)

        supportedPrivs = waitForDeferred(self.supportedPrivileges(request))
        yield supportedPrivs
        supportedPrivs = supportedPrivs.getResult()
        for item in supportedPrivs.children:
            assert (
                isinstance(item, davxml.SupportedPrivilege),
                "Not a SupportedPrivilege: %r" % (item,)
            )
            addSupportedPrivilege(item)

        # Steps 1 - 6
        got_deny = False
        for ace in new_acl.children:
            for old_ace in old_acl.children:
                if (ace.principal == old_ace.principal):
                    # Step 1
                    if old_ace.protected:
                        log.err("Attempt to overwrite protected ace %r on resource %r" % (old_ace, self))
                        yield (davxml.dav_namespace, "no-protected-ace-conflict")
                        return

                    # Step 2
                    #
                    # RFC3744 says that we either enforce the inherited ace
                    # conflict or we ignore it but use access control evaluation
                    # to determine whether there is any impact. Given that we
                    # have the "inheritable" behavior it does not make sense to
                    # disallow overrides of inherited ACEs since "inheritable"
                    # cannot itself be controlled via protocol.
                    #
                    # Otherwise, we'd use this logic:
                    #
                    #elif old_ace.inherited:
                    #    log.err("Attempt to overwrite inherited ace %r on resource %r" % (old_ace, self))
                    #    yield (davxml.dav_namespace, "no-inherited-ace-conflict")
                    #    return

            # Step 3
            if ace.allow and got_deny:
                log.err("Attempt to set grant ace %r after deny ace on resource %r" % (ace, self))
                yield (davxml.dav_namespace, "deny-before-grant")
                return
            got_deny = not ace.allow

            # Step 4: ignore as this server has no abstract privileges (FIXME: none yet?)

            # Step 5
            for privilege in ace.privileges:
                if privilege.children[0] not in supported:
                    log.err("Attempt to use unsupported privilege %r in ace %r on resource %r" % (privilege.children[0], ace, self))
                    yield (davxml.dav_namespace, "not-supported-privilege")
                    return
            if ace.protected:
                log.err("Attempt to create protected ace %r on resource %r" % (ace, self))
                yield (davxml.dav_namespace, "no-ace-conflict")
                return
            if ace.inherited:
                log.err("Attempt to create inherited ace %r on resource %r" % (ace, self))
                yield (davxml.dav_namespace, "no-ace-conflict")
                return

            # Step 6
            valid = waitForDeferred(self.validPrincipal(ace.principal, request))
            yield valid
            valid = valid.getResult()

            if not valid:
                log.err("Attempt to use unrecognized principal %r in ace %r on resource %r" % (ace.principal, ace, self))
                yield (davxml.dav_namespace, "recognized-principal")
                return

        # Step 8 & 9
        #
        # Iterate through the old ones and replace any that are in the new set, or remove
        # the non-inherited/non-protected not in the new set
        #
        new_aces = [ace for ace in new_acl.children]
        new_set = []
        for old_ace in old_acl.children:
            for i, new_ace in enumerate(new_aces):
                if self.samePrincipal(new_ace.principal, old_ace.principal):
                    new_set.append(new_ace)
                    del new_aces[i]
                    break
            else:
                if old_ace.protected and not old_ace.inherited:
                    new_set.append(old_ace)
        new_set.extend(new_aces)

        # Step 10
        # FIXME: verify acl is self-consistent

        # Step 11
        self.writeNewACEs(new_set)
        yield None

    mergeAccessControlList = deferredGenerator(mergeAccessControlList)
        
    def writeNewACEs(self, new_aces):
        """
        Write a new ACL to the resource's property store.
        This is a separate method so that it can be overridden by
        resources that need to do extra processing of ACLs being set
        via the ACL command.
        @param new_aces: C{list} of L{ACE} for ACL being set.
        """
        self.setAccessControlList(davxml.ACL(*new_aces))

    def matchPrivilege(self, privilege, ace_privileges, supportedPrivileges):
        for ace_privilege in ace_privileges:
            if privilege == ace_privilege or ace_privilege.isAggregateOf(privilege, supportedPrivileges):
                return True

        return False

    def checkPrivileges(self, request, privileges, recurse=False, principal=None, inherited_aces=None):
        """
        Check whether the given principal has the given privileges.
        (RFC 3744, section 5.5)
        @param request: the request being processed.
        @param privileges: an iterable of L{davxml.WebDAVElement} elements
            denoting access control privileges.
        @param recurse: C{True} if a recursive check on all child
            resources of this resource should be performed as well,
            C{False} otherwise.
        @param principal: the L{davxml.Principal} to check privileges
            for.  If C{None}, it is deduced from C{request} by calling
            L{currentPrincipal}.
        @param inherited_aces: a list of L{davxml.ACE}s corresponding to the precomputed
            inheritable aces from the parent resource hierarchy.
        @return: a L{Deferred} that callbacks with C{None} or errbacks with an
            L{AccessDeniedError}
        """
        if principal is None:
            principal = self.currentPrincipal(request)

        supportedPrivs = waitForDeferred(self.supportedPrivileges(request))
        yield supportedPrivs
        supportedPrivs = supportedPrivs.getResult()

        # Other principals types don't make sense as actors.
        assert (
            principal.children[0].name in ("unauthenticated", "href"),
            "Principal is not an actor: %r" % (principal,)
        )

        errors = []

        resources = [(self, None)]

        if recurse:
            x = self.findChildren("infinity", request, lambda x, y: resources.append((x,y)))
            x = waitForDeferred(x)
            yield x
            x.getResult()

        for resource, uri in resources:
            acl = waitForDeferred(resource.accessControlList(request, inherited_aces=inherited_aces))
            yield acl
            acl = acl.getResult()

            # Check for disabled
            if acl is None:
                errors.append((uri, list(privileges)))
                continue

            pending = list(privileges)
            denied = []

            for ace in acl.children:
                for privilege in tuple(pending):
                    if not self.matchPrivilege(davxml.Privilege(privilege), ace.privileges, supportedPrivs):
                        continue

                    match = waitForDeferred(self.matchPrincipal(principal, ace.principal, request))
                    yield match
                    match = match.getResult()

                    if match:
                        if ace.invert:
                            continue
                    else:
                        if not ace.invert:
                            continue

                    pending.remove(privilege)

                    if not ace.allow:
                        denied.append(privilege)

            denied += pending # If no matching ACE, then denied

            if denied: 
                errors.append((uri, denied))

        if errors:
            raise AccessDeniedError(errors,)
        
        yield None

    checkPrivileges = deferredGenerator(checkPrivileges)

    def supportedPrivileges(self, request):
        """
        See L{IDAVResource.supportedPrivileges}.

        This implementation returns a supported privilege set containing only
        the DAV:all privilege.
        """
        return succeed(allPrivilegeSet)

    def currentPrivileges(self, request):
        """
        See L{IDAVResource.currentPrivileges}.

        This implementation returns a current privilege set containing only
        the DAV:all privilege.
        """
        current = self.currentPrincipal(request)
        return self.privilegesForPrincipal(current, request)

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        """
        See L{IDAVResource.accessControlList}.

        This implementation looks up the ACL in the private property
        C{(L{twisted_private_namespace}, "acl")}.
        If no ACL has been stored for this resource, it returns the value
        returned by C{defaultAccessControlList}.
        If access is disabled it will return C{None}.
        """
        #
        # Inheritance is problematic. Here is what we do:
        #
        # 1. A private element <Twisted:inheritable> is defined for use inside
        #    of a <DAV:ace>. This private element is removed when the ACE is
        #    exposed via WebDAV.
        #
        # 2. When checking ACLs with inheritance resolution, the server must
        #    examine all parent resources of the current one looking for any
        #    <Twisted:inheritable> elements.
        #
        # If those are defined, the relevant ace is applied to the ACL on the
        # current resource.
        #
        myURL = None

        def getMyURL():
            url = request.urlForResource(self)

            assert url is not None, "urlForResource(self) returned None for resource %s" % (self,)

            return url

        try:
            acl = self.readDeadProperty(davxml.ACL)
        except HTTPError, e:
            assert (
                e.response.code == responsecode.NOT_FOUND,
                "Expected %s response from readDeadProperty() exception, not %s"
                % (responsecode.NOT_FOUND, e.response.code)
            )

            # Produce a sensible default for an empty ACL.
            if myURL is None:
                myURL = getMyURL()

            if myURL == "/":
                # If we get to the root without any ACLs, then use the default.
                acl = self.defaultAccessControlList()
            else:
                acl = davxml.ACL()

        # Dynamically update privileges for those ace's that are inherited.
        if inheritance:
            aces = list(acl.children)

            if myURL is None:
                myURL = getMyURL()

            if inherited_aces is None:
                if myURL != "/":
                    parentURL = parentForURL(myURL)
    
                    parent = waitForDeferred(request.locateResource(parentURL))
                    yield parent
                    parent = parent.getResult()
    
                    if parent:
                        parent_acl = waitForDeferred(
                            parent.accessControlList(request, inheritance=True, expanding=True)
                        )
                        yield parent_acl
                        parent_acl = parent_acl.getResult()
    
                        # Check disabled
                        if parent_acl is None:
                            yield None
                            return
    
                        for ace in parent_acl.children:
                            if ace.inherited:
                                aces.append(ace)
                            elif TwistedACLInheritable() in ace.children:
                                # Adjust ACE for inherit on this resource
                                children = list(ace.children)
                                children.remove(TwistedACLInheritable())
                                children.append(davxml.Inherited(davxml.HRef.fromString(parentURL)))
                                aces.append(davxml.ACE(*children))
            else:
                aces.extend(inherited_aces)

            # Always filter out any remaining private properties when we are
            # returning the ACL for the final resource after doing parent
            # inheritance.
            if not expanding:
                aces = [
                    davxml.ACE(*[
                        c for c in ace.children
                        if c != TwistedACLInheritable()
                    ])
                    for ace in aces
                ]

            acl = davxml.ACL(*aces)

        yield acl

    accessControlList = deferredGenerator(accessControlList)

    def inheritedACEsforChildren(self, request):
        """
        Do some optimisation of access control calculation by determining any inherited ACLs outside of
        the child resource loop and supply those to the checkPrivileges on each child.

        @param request: the L{IRequest} for the request in progress.
        @return:        a C{list} of L{Ace}s that child resources of this one will
            inherit and which will match the currently authenticated principal.
        """
        
        # Get the parent ACLs with inheritance and preserve the <inheritable> element.
        parent_acl = waitForDeferred(self.accessControlList(request, inheritance=True, expanding=True))
        yield parent_acl
        parent_acl = parent_acl.getResult()
        
        # Check disabled
        if parent_acl is None:
            yield None
            return

        # Filter out those that are not inheritable (and remove the inheritable element from those that are)
        aces = []
        for ace in parent_acl.children:
            if ace.inherited:
                aces.append(ace)
            elif TwistedACLInheritable() in ace.children:
                # Adjust ACE for inherit on this resource
                children = list(ace.children)
                children.remove(TwistedACLInheritable())
                children.append(davxml.Inherited(davxml.HRef.fromString(request.urlForResource(self))))
                aces.append(davxml.ACE(*children))
                
        # Filter out those that do not have a principal match with the current principal
        principal = self.currentPrincipal(request)
        filteredaces = []
        for ace in aces:
            if self.matchPrincipal(principal, ace.principal, request):
                if ace.invert:
                    continue
            else:
                if not ace.invert:
                    continue
            filteredaces.append(ace)
        yield filteredaces

    inheritedACEsforChildren = deferredGenerator(inheritedACEsforChildren)

    def inheritedACLSet(self):
        """
        @return: a sequence of L{davxml.HRef}s from which ACLs are inherited.

        This implementation returns an empty set.
        """

        return []

    def findPrincipalForAuthID(self, request, authid):
        """
        @param request: the L{IRequest} for the request in progress.
        @param authid: a string containing the
            authentication/authorization identifier for the principal
            to lookup.
        @return: a deferred tuple of C{(principal, principalURI)}
            where: C{principal} is the L{Principal} that is found;
            C{principalURI} is the C{str} URI of the principal. 
            It will errback with an HTTPError(responsecode.FORBIDDEN) if
            the principal isn't found.
        """
        # Try to match principals in each principal collection on the resource
        collections = waitForDeferred(self.principalCollections(request))
        yield collections
        collections = collections.getResult()

        for collection in collections:
            principalURI = joinURL(str(collection), authid)

            principal = waitForDeferred(request.locateResource(principalURI))
            yield principal
            principal = principal.getResult()

            if isPrincipalResource(principal):
                yield (principal, principalURI)
                return
        else:
            principalCollections = waitForDeferred(self.principalCollections(request))
            yield principalCollections
            principalCollections = principalCollections.getResult()

            if len(principalCollections) == 0:
                log.msg("DAV:principal-collection-set property cannot be found on the resource being authorized: %s" % self)
            else:
                log.msg("Could not find principal matching user id: %s" % authid)
            raise HTTPError(responsecode.FORBIDDEN)

    findPrincipalForAuthID = deferredGenerator(findPrincipalForAuthID)

    def samePrincipal(self, principal1, principal2):
        """
        Check whether the two prinicpals are exactly the same in terms of
        elements and data.
        @param principal1: a L{Principal} to test.
        @param principal2: a L{Principal} to test.
        @return: C{True} if they are the same, C{False} otherwise.
        """

        # The interesting part of a principal is it's one child
        principal1 = principal1.children[0]
        principal2 = principal2.children[0]

        if type(principal1) == type(principal2):
            if isinstance(principal1, davxml.Property):
                return type(principal1.children[0]) == type(principal2.children[0])
            elif isinstance(principal1, davxml.HRef):
                return str(principal1.children[0]) == str(principal2.children[0])
            else:
                return True
        else:
            return False
                
    def matchPrincipal(self, principal1, principal2, request):

        """
        Check whether the principal1 is a principal in the set defined by
        principal2.
        @param principal1: a L{Principal} to test. C{principal1} must contain
            a L{davxml.HRef} or L{davxml.Unauthenticated} element.
        @param principal2: a L{Principal} to test.
        @param request: the request being processed.
        @return: C{True} if they match, C{False} otherwise.
        """
        # See RFC 3744, section 5.5.1

        principals = (principal1, principal2)

        # The interesting part of a principal is it's one child
        principal1, principal2 = [p.children[0] for p in principals]

        if isinstance(principal2, davxml.All):
            yield True
            return

        elif isinstance(principal2, davxml.Authenticated):
            if isinstance(principal1, davxml.Unauthenticated):
                yield False
                return
            else:
                yield True
                return

        elif isinstance(principal2, davxml.Unauthenticated):
            if isinstance(principal1, davxml.Unauthenticated):
                yield True
                return
            else:
                yield False
                return

        elif isinstance(principal1, davxml.Unauthenticated):
            yield False
            return

        assert (
            isinstance(principal1, davxml.HRef),
            "Not an HRef: %r" % (principal1,)
        )

        principal2 = waitForDeferred(self.resolvePrincipal(principal2, request))
        yield principal2
        principal2 = principal2.getResult()

        assert principal2 is not None, "principal2 is None"


        # Compare two HRefs and do group membership test as well
        if principal1 == principal2:
            yield True
            return
         
        ismember = waitForDeferred(self.principalIsGroupMember(str(principal1), str(principal2), request))
        yield ismember
        ismember = ismember.getResult()

        if ismember:
            yield True
            return
  
        yield False

    matchPrincipal = deferredGenerator(matchPrincipal)

    def principalIsGroupMember(self, principal1, principal2, request):
        """
        Check whether one principal is a group member of another.
        
        @param principal1: C{str} principalURL for principal to test.
        @param principal2: C{str} principalURL for possible group principal to test against.
        @param request: the request being processed.
        @return: L{Deferred} with result C{True} if principal1 is a member of principal2, C{False} otherwise
        """
        
        def testGroup(group):
            # Get principal resource for principal2
            if group and isinstance(group, DAVPrincipalResource):
                members = group.groupMembers()
                if principal1 in members:
                    return True
                
            return False

        d = request.locateResource(principal2)
        d.addCallback(testGroup)
        return d
        
    def validPrincipal(self, ace_principal, request):
        """
        Check whether the supplied principal is valid for this resource.
        @param ace_principal: the L{Principal} element to test
        @param request: the request being processed.
        @return C{True} if C{ace_principal} is valid, C{False} otherwise.

        This implementation tests for a valid element type and checks for an
        href principal that exists inside of a principal collection.
        """
        def defer():
            #
            # We know that the element contains a valid element type, so all
            # we need to do is check for a valid property and a valid href.
            #
            real_principal = ace_principal.children[0]

            if isinstance(real_principal, davxml.Property):
                # See comments in matchPrincipal().  We probably need some common code.
                log.err("Encountered a property principal (%s), but handling is not implemented.  Invalid for ACL use."
                        % (real_principal,))
                return False

            if isinstance(real_principal, davxml.HRef):
                return self.validHrefPrincipal(real_principal, request)

            return True

        return maybeDeferred(defer)

    def validHrefPrincipal(self, href_principal, request):
        """
        Check whether the supplied principal (in the form of an Href)
        is valid for this resource.
        @param href_principal: the L{Href} element to test
        @param request: the request being processed.
        @return C{True} if C{href_principal} is valid, C{False} otherwise.

        This implementation tests for a href element that corresponds to
        a principal resource.
        """
        # Must have the principal resource type
        d = request.locateResource(str(href_principal))
        d.addCallback(isPrincipalResource)
        return d

    def resolvePrincipal(self, principal, request):
        """
        Resolves a L{davxml.Principal} element into a L{davxml.HRef} element
        if possible.  Specifically, the given C{principal}'s contained
        element is resolved.

        L{davxml.Property} is resolved to the URI in the contained property.

        L{davxml.Self} is resolved to the URI of this resource.

        L{davxml.HRef} elements are returned as-is.

        All other principals, including meta-principals (eg. L{davxml.All}),
        resolve to C{None}.

        @param principal: the L{davxml.Principal} child element to resolve.
        @param request: the request being processed.
        @return: a deferred L{davxml.HRef} element or C{None}.
        """

        if isinstance(principal, davxml.Property):
            # raise NotImplementedError("Property principals are not implemented.")
            #
            # We can't raise here without potentially crippling the server in a way
            # that can't be fixed over the wire, so let's refuse the match and log
            # an error instead.
            #
            # Note: When fixing this, also fix validPrincipal()
            #
            log.err("Encountered a property principal (%s), but handling is not implemented; invalid for ACL use."
                    % (principal,))
            yield None
            return

            #
            # FIXME: I think this is wrong - we need to get the
            # namespace and name from the first child of DAV:property
            #
            namespace = principal.attributes.get(["namespace"], dav_namespace)
            name = principal.attributes["name"]

            principal = waitForDeferred(self.readProperty((namespace, name), request))
            yield principal
            try:
                principal = principal.getResult()
            except HTTPError, e:
                assert (
                    e.response.code == responsecode.NOT_FOUND,
                    "Expected %s response from readProperty() exception, not %s"
                    % (responsecode.NOT_FOUND, e.response.code)
                )
                yield None
                return

            if not isinstance(principal, davxml.Principal):
                log.err("Non-principal value in property {%s}%s referenced by property principal."
                        % (namespace, name))
                yield None
                return

            if len(principal.children) != 1:
                yield None
                return

            # The interesting part of a principal is it's one child
            principal = principal.children[0]

        elif isinstance(principal, davxml.Self):
            try:
                self = IDAVPrincipalResource(self)
            except TypeError:
                log.err("DAV:self ACE is set on non-principal resource %r" % (self,))
                yield None
                return
            principal = davxml.HRef.fromString(self.principalURL())

        if isinstance(principal, davxml.HRef):
            yield principal
        else:
            yield None

        assert (
            isinstance(principal, (davxml.All, davxml.Authenticated, davxml.Unauthenticated)),
            "Not a meta-principal: %r" % (principal,)
        )

    resolvePrincipal = deferredGenerator(resolvePrincipal)

    def privilegesForPrincipal(self, principal, request):
        """
        See L{IDAVResource.privilegesForPrincipal}.
        """
        # NB Return aggregate privileges expanded.

        acl = waitForDeferred(self.accessControlList(request))
        yield acl
        acl = acl.getResult()

        # Check disabled
        if acl is None:
            yield []

        granted = []
        denied = []
        for ace in acl.children:
            # First see if the ace's principal affects the principal being tested.
            # FIXME: support the DAV:invert operation

            match = waitForDeferred(self.matchPrincipal(principal, ace.principal, request))
            yield match
            match = match.getResult()

            if match:
                # Expand aggregate privileges
                ps = []
                supportedPrivs = waitForDeferred(self.supportedPrivileges(request))
                yield supportedPrivs
                supportedPrivs = supportedPrivs.getResult()
                for p in ace.privileges:
                    ps.extend(p.expandAggregate(supportedPrivs))

                # Merge grant/deny privileges
                if ace.allow:
                    granted.extend([p for p in ps if p not in granted])
                else:
                    denied.extend([p for p in ps if p not in denied])

        # Subtract denied from granted
        allowed = [p for p in granted if p not in denied]

        yield allowed

    privilegesForPrincipal = deferredGenerator(privilegesForPrincipal)

    def matchACEinACL(self, acl, ace):
        """
        Find an ACE in the ACL that matches the supplied ACE's principal.
        @param acl: the L{ACL} to look at.
        @param ace: the L{ACE} to try and match
        @return:    the L{ACE} in acl that matches, None otherwise.
        """
        for a in acl.children:
            if self.samePrincipal(a.principal, ace.principal):
                return a
        
        return None
    
    def principalSearchPropertySet(self):
        """
        @return: a L{davxml.PrincipalSearchPropertySet} element describing the
        principal properties that can be searched on this principal collection,
        or C{None} if this is not a principal collection.
        
        This implementation returns None. Principal collection resources must
        override and return their own suitable response.
        """
        return None

    ##
    # HTTP
    ##

    def renderHTTP(self, request):
        # FIXME: This is for testing with litmus; comment out when not in use
        #litmus = request.headers.getRawHeaders("x-litmus")
        #if litmus: log.msg("*** Litmus test: %s ***" % (litmus,))

        # FIXME: Learn how to use twisted logging facility, wsanchez
        protocol = "HTTP/%s.%s" % request.clientproto
        log.msg("%s %s %s" % (request.method, urllib.unquote(request.uri), protocol))

        #
        # If this is a collection and the URI doesn't end in "/", redirect.
        #
        if self.isCollection() and request.uri[-1:] != "/":
            return RedirectResponse(request.uri + "/")

        def setHeaders(response):
            response = IResponse(response)

            response.headers.setHeader("dav", self.davComplianceClasses())

            #
            # If this is a collection and the URI doesn't end in "/", add a
            # Content-Location header.  This is needed even if we redirect such
            # requests (as above) in the event that this resource was created or
            # modified by the request.
            #
            if self.isCollection() and request.uri[-1:] != "/":
                response.headers.setHeader("content-location", request.uri + "/")

            return response

        def onError(f):
            # If we get an HTTPError, run its response through setHeaders() as
            # well.
            f.trap(HTTPError)
            return setHeaders(f.value.response)

        d = maybeDeferred(super(DAVResource, self).renderHTTP, request)
        return d.addCallbacks(setHeaders, onError)

class DAVLeafResource (DAVResource, LeafResource):
    """
    DAV resource with no children.
    """
    def findChildren(self, depth, request, callback, privileges=None, inherited_aces=None):
        return succeed(None)

class DAVPrincipalResource (DAVLeafResource):
    """
    Resource representing a WebDAV principal.  (RFC 3744, section 2)
    """
    implements(IDAVPrincipalResource)

    ##
    # WebDAV
    ##

    liveProperties = DAVLeafResource.liveProperties + (
        (dav_namespace, "alternate-URI-set"),
        (dav_namespace, "principal-URL"    ),
        (dav_namespace, "group-member-set" ),
        (dav_namespace, "group-membership" ),
    )

    def davComplianceClasses(self):
        return ("1",)

    def isCollection(self):
        return False

    def findChildren(self, depth, request, callback, privileges=None, inherited_aces=None):
        return succeed(None)

    def readProperty(self, property, request):
        def defer():
            if type(property) is tuple:
                qname = property
            else:
                qname = property.qname()

            namespace, name = qname

            if namespace == dav_namespace:
                if name == "alternate-URI-set":
                    return davxml.AlternateURISet(*[davxml.HRef(u) for u in self.alternateURIs()])

                if name == "principal-URL":
                    return davxml.PrincipalURL(davxml.HRef(self.principalURL()))

                if name == "group-member-set":
                    return davxml.GroupMemberSet(*[davxml.HRef(p) for p in self.groupMembers()])

                if name == "group-membership":
                    return davxml.GroupMembership(*[davxml.HRef(g) for g in self.groupMemberships()])

                if name == "resourcetype":
                    if self.isCollection():
                        return davxml.ResourceType(davxml.Collection(), davxml.Principal())
                    else:
                        return davxml.ResourceType(davxml.Principal())

            return super(DAVPrincipalResource, self).readProperty(qname, request)

        return maybeDeferred(defer)

    ##
    # ACL
    ##

    def alternateURIs(self):
        """
        See L{IDAVPrincipalResource.alternateURIs}.

        This implementation returns C{()}.  Subclasses should override this
        method to provide alternate URIs for this resource if appropriate.
        """
        return ()

    def principalURL(self):
        """
        See L{IDAVPrincipalResource.principalURL}.

        This implementation raises L{NotImplementedError}.  Subclasses must
        override this method to provide the principal URL for this resource.
        """
        unimplemented(self)

    def groupMembers(self):
        """
        See L{IDAVPrincipalResource.groupMembers}.

        This implementation returns C{()}, which is appropriate for non-group
        principals.  Subclasses should override this method to provide member
        URLs for this resource if appropriate.
        """
        return ()

    def groupMemberships(self):
        """
        See L{IDAVPrincipalResource.groupMemberships}.

        This implementation raises L{NotImplementedError}.  Subclasses must
        override this method to provide the group URLs for this resource.
        """
        unimplemented(self)

    def principalMatch(self, href):
        """
        Check whether the supplied principal matches this principal or is a
        member of this principal resource.
        @param href: the L{HRef} to test.
        @return:     True if there is a match, False otherwise
        """
        uri = str(href)
        if self.principalURL() == uri:
            return True
        else:
            return uri in self.groupMembers()

class AccessDeniedError(Exception):
    def __init__(self, errors):
        """ 
        An error to be raised when some request fails to meet sufficient access 
        privileges for a resource.

        @param errors: sequence of tuples, one for each resource for which one or
            more of the given privileges are not granted, in the form
            C{(uri, privileges)}, where uri is a URL path relative to
            resource or C{None} if the error was in this resource,
            privileges is a sequence of the privileges which are not
            granted a subset thereof.
        """
        Exception.__init__(self, "Access denied for some resources: %r" % (errors,))
        self.errors = errors

##
# Utilities
##

def isPrincipalResource(resource):
    try:
        resource = IDAVPrincipalResource(resource)
    except TypeError:
        return False
    else:
        return True

class TwistedACLInheritable (davxml.WebDAVEmptyElement):
    """
    When set on an ACE, this indicates that the ACE privileges should be inherited by
    all child resources within the resource with this ACE.
    """
    namespace = twisted_dav_namespace
    name = "inheritable"

davxml.registerElement(TwistedACLInheritable)
davxml.ACE.allowed_children[(twisted_dav_namespace, "inheritable")] = (0, 1)

allACL = davxml.ACL(
    davxml.ACE(
        davxml.Principal(davxml.All()),
        davxml.Grant(davxml.Privilege(davxml.All())),
        davxml.Protected(),
        TwistedACLInheritable()
    )
)

readonlyACL = davxml.ACL(
    davxml.ACE(
        davxml.Principal(davxml.All()),
        davxml.Grant(davxml.Privilege(davxml.Read())),
        davxml.Protected(),
        TwistedACLInheritable()
    )
)

allPrivilegeSet = davxml.SupportedPrivilegeSet(
    davxml.SupportedPrivilege(
        davxml.Privilege(davxml.All()),
        davxml.Description("all privileges", **{"xml:lang": "en"})
    )
)

#
# This is one possible graph of the "standard" privileges documented
# in 3744, section 3.
#
davPrivilegeSet = davxml.SupportedPrivilegeSet(
    davxml.SupportedPrivilege(
        davxml.Privilege(davxml.All()),
        davxml.Description("all privileges", **{"xml:lang": "en"}),
        davxml.SupportedPrivilege(
            davxml.Privilege(davxml.Read()),
            davxml.Description("read resource", **{"xml:lang": "en"}),
        ),
        davxml.SupportedPrivilege(
            davxml.Privilege(davxml.Write()),
            davxml.Description("write resource", **{"xml:lang": "en"}),
            davxml.SupportedPrivilege(
                davxml.Privilege(davxml.WriteProperties()),
                davxml.Description("write resource properties", **{"xml:lang": "en"}),
            ),
            davxml.SupportedPrivilege(
                davxml.Privilege(davxml.WriteContent()),
                davxml.Description("write resource content", **{"xml:lang": "en"}),
            ),
            davxml.SupportedPrivilege(
                davxml.Privilege(davxml.Bind()),
                davxml.Description("add child resource", **{"xml:lang": "en"}),
            ),
            davxml.SupportedPrivilege(
                davxml.Privilege(davxml.Unbind()),
                davxml.Description("remove child resource", **{"xml:lang": "en"}),
            ),
        ),
        davxml.SupportedPrivilege(
            davxml.Privilege(davxml.Unlock()),
            davxml.Description("unlock resource without ownership of lock", **{"xml:lang": "en"}),
        ),
        davxml.SupportedPrivilege(
            davxml.Privilege(davxml.ReadACL()),
            davxml.Description("read resource access control list", **{"xml:lang": "en"}),
        ),
        davxml.SupportedPrivilege(
            davxml.Privilege(davxml.WriteACL()),
            davxml.Description("write resource access control list", **{"xml:lang": "en"}),
        ),
        davxml.SupportedPrivilege(
            davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
            davxml.Description("read privileges for current principal", **{"xml:lang": "en"}),
        ),
    ),
)

unauthenticatedPrincipal = davxml.Principal(davxml.Unauthenticated())
