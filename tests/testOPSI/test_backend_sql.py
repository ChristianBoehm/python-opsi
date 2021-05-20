# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing opsi SQL backend.
"""

import os.path

import pytest

import OPSI.Backend.SQL as sql
import OPSI.Object as ob

from .helpers import cleanMandatoryConstructorArgsCache as cmcac
from .helpers import createTemporaryTestfile


@pytest.fixture
def sqlBackendWithoutConnection():
	backend = sql.SQLBackend()
	backend._sql = sql.SQL()

	yield backend


def testCreatingFilterWithoutParameters(sqlBackendWithoutConnection):
	assert '' == sqlBackendWithoutConnection._filterToSql()


def testCreatingFilterHasParentheses(sqlBackendWithoutConnection):
	query = sqlBackendWithoutConnection._filterToSql({'lol': False})
	assert '`lol` = 0' in query
	assert query.startswith('(')
	assert query.endswith(')')


def testCreatingNoFilterForNone(sqlBackendWithoutConnection):
	result = sqlBackendWithoutConnection._filterToSql({'a': False, 'b': None})
	assert 'a' in result
	assert 'b' not in result
	assert 'NULL' not in result
	assert 'None' not in result


def testCreatingFilterForNoneInList(sqlBackendWithoutConnection):
	assert '`a` is NULL' in sqlBackendWithoutConnection._filterToSql({'a': [None]})


@pytest.mark.parametrize("filterExpression", [{'a': []}])
def testFilterCreationSkiptsEmptyLists(sqlBackendWithoutConnection, filterExpression):
	resultingQuery = sqlBackendWithoutConnection._filterToSql(filterExpression)

	assert filterExpression
	for key in filterExpression:
		assert key not in resultingQuery

	assert '' == resultingQuery


@pytest.mark.parametrize("expectedConversion, filterExpression", [
	('0', {'a': False}),
	('1', {'a': True})
])
def testBoolValueRepresentation(sqlBackendWithoutConnection, expectedConversion, filterExpression):
	assert expectedConversion in sqlBackendWithoutConnection._filterToSql(filterExpression)


def testCreateFilterForMultipleBools(sqlBackendWithoutConnection):
	condition = sqlBackendWithoutConnection._filterToSql({'a': True, 'b': False})
	first, second = condition.split(' and ', 1)

	assert (first == '(`a` = 1)' and second == '(`b` = 0)') or (second == '(`a` = 1)' and first == '(`b` = 0)')


def testCreatingFilterAddsMultipleValuesWithAnAnd(sqlBackendWithoutConnection):
	assert u' and ' in sqlBackendWithoutConnection._filterToSql({'a': True, 'b': False})


@pytest.mark.parametrize("result, filterExpression", [
	('(`a` = 1)', {'a': 1}),
	('(`b` = 2.3)', {'b': 2.3}),
	('(`c` = 4)', {'c': 4}),
])
def testCreatingFilterForNumberRepresentation(sqlBackendWithoutConnection, result, filterExpression):
	assert result == sqlBackendWithoutConnection._filterToSql(filterExpression)


def testCreatingFilterForStringValue(sqlBackendWithoutConnection):
	assert "(`a` = 'b')" == sqlBackendWithoutConnection._filterToSql({'a': "b"})


def testCreatingFilterWithListOfValuesCreatesAnOrExpression(sqlBackendWithoutConnection):
	assert '(`a` = 1 or `a` = 2)' == sqlBackendWithoutConnection._filterToSql({'a': [1, 2]})


def testCreatingFilterWithMultipleParameters(sqlBackendWithoutConnection):
	# Expected is something like: '(`a` = 1 or `a` = 2) and (`b` = 0)'
	result = sqlBackendWithoutConnection._filterToSql({'a': [1, 2], 'b': False})

	first, second = result.split(' and ')

	def testOrCondition(condition):
		ffirst, fsecond = condition.split(' or ')
		assert ffirst == '(`a` = 1'
		assert fsecond == '`a` = 2)'

	if second == '(`b` = 0)':
		testOrCondition(first)
	elif first == '(`b` = 0)':
		testOrCondition(second)
	else:
		raise RuntimeError("We should never get here!")


def testCreatingFilterWithWildcard(sqlBackendWithoutConnection):
	assert u"(`a` LIKE '%bc')" == sqlBackendWithoutConnection._filterToSql({'a': '*bc'})


@pytest.mark.parametrize("result, filterExpression", [
	(u"(`a` > 1)", {'a': '> 1'}),
	(u"(`a` < 1)", {'a': '< 1'}),
	(u"(`a` = 1)", {'a': '= 1'}),
	(u"(`a` <=> 1)", {'a': '<=> 1'}),
])
def testCreatingFilterWithGreaterOrLowerOrEqualSign(sqlBackendWithoutConnection, result, filterExpression):
	assert result == sqlBackendWithoutConnection._filterToSql(filterExpression)


def testCreatingQueryIncludesTableName(sqlBackendWithoutConnection):
	assert "foo" in sqlBackendWithoutConnection._createQuery('foo')


def testQueryCreationWithoutAttributesEverythingIsSelected(sqlBackendWithoutConnection):
	assert u'select * from' in sqlBackendWithoutConnection._createQuery('foo')


def testQueryCreationDefiningColumnsToSelect(sqlBackendWithoutConnection):
	assert u'`first`,`second`' in sqlBackendWithoutConnection._createQuery('foo', ['first', 'second'])


def testQueryCreationHavingFilterAddsWhereClause(sqlBackendWithoutConnection):
	assert u'where' not in sqlBackendWithoutConnection._createQuery('foo')
	assert u'where' in sqlBackendWithoutConnection._createQuery('foo', filter={'a': 1})


@pytest.fixture
def cleanMandatoryConstructorArgsCache():
	with cmcac():
		yield


def testUniqueConditionForHostObject(sqlBackendWithoutConnection, cleanMandatoryConstructorArgsCache):
	host = ob.Host('foo.bar.baz')
	assert "`hostId` = 'foo.bar.baz'" == sqlBackendWithoutConnection._uniqueCondition(host)


def testUniqueConditionOptionalParametersAreIgnored(sqlBackendWithoutConnection, cleanMandatoryConstructorArgsCache):
	host = ob.Host('foo.bar.baz', inventoryNumber='ABC+333')

	assert "`hostId` = 'foo.bar.baz'" == sqlBackendWithoutConnection._uniqueCondition(host)


def testUniqueConditionMultipleParametersAreJoinedWithAnAnd(sqlBackendWithoutConnection, cleanMandatoryConstructorArgsCache):
	softwareLicense = ob.SoftwareLicense('a', 'b')
	condition = sqlBackendWithoutConnection._uniqueCondition(softwareLicense)

	assert ' and ' in condition
	assert "`softwareLicenseId` = 'a' and `licenseContractId` = 'b'" == condition


def testUniqueConditionForHostGroupHasTypeAppended(sqlBackendWithoutConnection, cleanMandatoryConstructorArgsCache):
	group = ob.ProductGroup('t')
	condition = sqlBackendWithoutConnection._uniqueCondition(group)

	assert "`groupId` = 't'" in condition
	assert "and" in condition
	assert "`type` = 'ProductGroup'" in condition


def testUniqueConditionForProductGroupHasTypeAppended(sqlBackendWithoutConnection, cleanMandatoryConstructorArgsCache):
	group = ob.HostGroup('hg')
	condition = sqlBackendWithoutConnection._uniqueCondition(group)

	assert "`groupId` = 'hg'" in condition
	assert "and" in condition
	assert "`type` = 'HostGroup'" in condition


def testUniqueConditionForBooleanParameters(sqlBackendWithoutConnection, cleanMandatoryConstructorArgsCache):
	class Foo:
		def __init__(self, true, false):
			self.true = true
			self.false = false

	condition = sqlBackendWithoutConnection._uniqueCondition(Foo(True, False))

	assert "`true` = 1" in condition
	assert "and" in condition
	assert "`false` = 0" in condition


def testAccessingParametersWithAttributenamesFails(sqlBackendWithoutConnection, cleanMandatoryConstructorArgsCache):
	class Foo2:
		def __init__(self, something):
			self._something = something

	with pytest.raises(AttributeError):
		sqlBackendWithoutConnection._uniqueCondition(Foo2(True))


def testUniqueConditionMandatoryParametersAreSkippedIfValueIsNone(sqlBackendWithoutConnection, cleanMandatoryConstructorArgsCache):
	assert '' == sqlBackendWithoutConnection._uniqueCondition(FooParam(None))


@pytest.mark.parametrize("number", [1, 2.3, 4])
def testParameterIsNumber(sqlBackendWithoutConnection, number, cleanMandatoryConstructorArgsCache):
	assert '`param` = {0!s}'.format(number) == sqlBackendWithoutConnection._uniqueCondition(FooParam(number))


class FooParam:
	def __init__(self, param):
		self.param = param


def testCreatingUniqueHardwareConditionIgnoresHardwareClassAndType(sqlBackendWithoutConnection):
	hwDict = {
		"hardwareClass": "abc",
		"type": 'def'
	}

	assert '' == sqlBackendWithoutConnection._uniqueAuditHardwareCondition(hwDict)


def testCreatingConditionWithNoneTypes(sqlBackendWithoutConnection):
	testDict = {
		"abc": None,
		'def': [None]
	}

	condition = sqlBackendWithoutConnection._uniqueAuditHardwareCondition(testDict)
	assert u'`abc` is NULL' in condition
	assert u' and ' in condition
	assert u'`def` is NULL' in condition


def testAddingMultipleParametersWithAnd(sqlBackendWithoutConnection):
	testDict = {
		"abc": None,
		'def': [None]
	}

	condition = sqlBackendWithoutConnection._uniqueAuditHardwareCondition(testDict)
	assert u' and ' in condition
	assert not condition.strip().endswith('and')
	assert not condition.strip().startswith('and')


def testCreatingQueryWithVariousTypes(sqlBackendWithoutConnection):
	testDict = {
		"int": 1,
		"float": 2.3,
		"long": 4,
		"bool_true": True,
		"bool_false": False,
		"string": "caramba",
	}

	condition = sqlBackendWithoutConnection._uniqueAuditHardwareCondition(testDict)
	assert u' and ' in condition
	assert u'`int` = 1' in condition
	assert u'`float` = 2.3' in condition
	assert u'`long` = 4' in condition
	assert u'`bool_false` = False' in condition
	assert u'`bool_true` = True' in condition
	assert u"`string` = 'caramba'" in condition


@pytest.mark.parametrize("query", ["SELECT something"])
def testAvoidingMaliciousQueryOnlySelectAllowed(query):
	assert query == returnQueryAfterCheck(query)


@pytest.mark.parametrize("query", [
	"ALTER TABLE blabla",
	"DROP TABLE blabla"
])
def testOnlySelectAllowedRaisesExceptionWithNonSelectQuery(query):
	with pytest.raises(ValueError):
		returnQueryAfterCheck(query)


def returnQueryAfterCheck(query):
	sql.onlyAllowSelect(query)
	return query


def testAlteringTableAfterChangeOfHardwareAuditConfig(sqlBackendCreationContextManager):
	"""
	Test if adding and altering hardware audit tables works.

	We must be able to alter the table after a change of the hardware
	audit configuration took place. This is a commong operation during
	updates.
	"""
	configDir = os.path.join(os.path.dirname(__file__), 'testdata', 'backend')
	pathToOldConfig = os.path.join(configDir, 'small_hwaudit.conf')
	pathToNewConfig = os.path.join(configDir, 'small_extended_hwaudit.conf')

	with createTemporaryTestfile(pathToOldConfig) as oldConfig:
		with sqlBackendCreationContextManager(auditHardwareConfigFile=oldConfig) as backend:
			backend.backend_createBase()

			with createTemporaryTestfile(pathToNewConfig) as newConfig:
				backend._auditHardwareConfigFile = newConfig
				backend._setAuditHardwareConfig(backend.auditHardware_getConfig())

				backend.backend_createBase()
