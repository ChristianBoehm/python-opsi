

import time, threading

from OPSI.Util.Thread import *
from opsidevtools.unittest.lib.unittest2.case import TestCase

class ThreadTestCase(TestCase):
	
	def setUp(self):
		self.pool = ThreadPool(autostart=False)
		self.pool.start()
		
	def test_WorkerCreation(self):
		self.pool.adjustSize(size=10)
		self.assertEqual(10, len(self.pool.worker), "Expected %s worker to be in pool, but found %s" % (10, len(self.pool.worker)))

	def test_stopPool(self):
		self.pool.adjustSize(size=10)
		for i in range(5):
			time.sleep(1)
		numThreads = threading.activeCount() - len(self.pool.worker)
		self.pool.stop()
		
		self.assertEqual(0, len(self.pool.worker), "Expected %s worker to be in pool, but found %s" % (0, len(self.pool.worker)))
		self.assertFalse(self.pool.started, "Expected pool to have stopped, but it hasn't")
		self.assertEqual(threading.activeCount(), numThreads, "Expected %s thread to be alive, but got %s" % (numThreads, threading.activeCount()))
		
	def test_workerCallback(self):
		self.pool.adjustSize(2)
		
		result = []
		def assertCallback(success, returned, errors):
			result.append(success)
			result.append(returned)
			result.append(errors)
        
        
		self.pool.addJob(function=(lambda: 'test'), callback=assertCallback)
		
		#give thread time to finish
		time.sleep(1)
		
		self.assertTrue(result[0], "Expected callback success to be 'True', but got %s"%result[0])
		self.assertEqual(result[1], 'test', "Expected callback result to be 'test', but got %s"%result[1])
		self.assertIsNone(result[2], "Expected function to run successfully, but got error %s"% result[2])
		
		
	def test_workerCallbackWithException(self):
		self.pool.adjustSize(2)
		
		result = []
		def assertCallback(success, returned, errors):
			result.append(success)
			result.append(returned)
			result.append(errors)
        
        
		def raiseError():
			raise Exception("TestException")
        
		self.pool.addJob(function=raiseError, callback=assertCallback)
		
		#give thread time to finish
		time.sleep(1)
		
		self.assertFalse(result[0], "Expected callback success to be 'False', but got %s"%result[0])
		self.assertIsNone(result[1], "Expected callback to return no result, but got %s"%result[1])
		self.assertIsNotNone(result[2], "Expected function to run successfully, but got error %s"% result[2])
        
	def test_invalidThreadPoolSize(self):
		try:
			self.pool.adjustSize(-1)
			self.fail("ThreadPool has an invalid size, but no exception was raised.")
		except ThreadPoolException, e:
			return
		except Exception, e:
			self.fail(e)
			
	def test_adjustPoolSize(self):
		self.pool.adjustSize(size=2)
		self.pool.adjustSize(size=10)
		
		time.sleep(1)
		
		self.assertEqual(10, self.pool.size, "Expected pool size to be %s, but got %s." % (10 , self.pool.size))
		self.assertEqual(10, len(self.pool.worker), "Expected %s worker to be in pool, but found %s" %(10, len(self.pool.worker)))
		
		self.pool.adjustSize(size=2)
		
		self.assertEqual(2, self.pool.size, "Expected pool size to be %s, but got %s." % (2 , self.pool.size))
		self.assertEqual(2, len(self.pool.worker), "Expected %s worker to be in pool, but found %s" % (2, len(self.pool.worker)))
		
	def test_floodPool(self):
		self.pool.adjustSize(2)
		
		results = []
		def callback(success, returned, errors):
			results.append(success)
		
		def waitJob():
			for i in range(3):
				time.sleep(1)
			
		for i in range(5):
			self.pool.addJob(waitJob, callback=callback)
			
		self.assertEquals(2, len(self.pool.worker), "Expected %s worker in pool, but got %s" % (2, len(self.pool.worker)))
		self.assertGreater(self.pool.jobQueue.unfinished_tasks, len(self.pool.worker), "Expected more tasks in Queue than workers in pool, but got %s tasks and %s worker" % (self.pool.jobQueue.unfinished_tasks, len(self.pool.worker)))
		
		for i in range(10):
			time.sleep(1)
		self.assertEquals(5, len(results), "Expected %s results but, but got %s" % (5, len(results)))
        
	def test_globalPool(self):
		pool = getGlobalPool()
		self.assertTrue(isinstance(pool, ThreadPool), "Expected %s to be a ThreadPool instance." % pool)
        
        def test_dutyAfterNoDuty(self):
        	self.pool.adjustSize(5)
        	self.pool.stop()
        	self.pool.start()
        	
        	results = []
		def callback(success, returned, errors):
			results.append(success)
		
		def shortJob():
			x = 10*10
		
		for i in range(10):
			self.pool.addJob(shortJob, callback=callback)
		
		time.sleep(1)
		self.assertEquals(10, len(results), "Expected %s results, but got %s" % (10, len(results)))
		
		time.sleep(1)
		time.sleep(1)
		results = []
		for i in range(10):
			self.pool.addJob(shortJob, callback=callback)
		time.sleep(1)
		self.assertEquals(10, len(results), "Expected %s results, but got %s" % (10, len(results)))
	
	def test_grow(self):
		self.pool.adjustSize(2)
		self.pool.stop()
        	self.pool.start()
        	
        	results = []
		def callback(success, returned, errors):
			results.append(success)
		
        	def sleepJob():
			time.sleep(3)
		
		for i in range(20):
			self.pool.addJob(sleepJob, callback=callback)
		time.sleep(4)
		self.assertEqual(len(results), 2, "Expected %s results, but got %s" % (2, len(results)))
		
		self.pool.adjustSize(20)
		time.sleep(4)
		self.assertEquals(len(results), 20, "Expected %s results, but got %s" % (20, len(results)))
	
	def test_shrink(self):
		self.pool.adjustSize(5)
		self.pool.stop()
        	self.pool.start()
        	
        	results = []
		def callback(success, returned, errors):
			results.append(success)
		
        	def sleepJob():
			time.sleep(3)
		
		for i in range(12):
			self.pool.addJob(sleepJob, callback=callback)
		time.sleep(4)
		self.assertEqual(len(results), 5, "Expected %s results, but got %s" % (5, len(results)))
		
		self.pool.adjustSize(1)
		time.sleep(3)
		self.assertEquals(len(results), 10,  "Expected %s results, but got %s" % (10, len(results)))
		time.sleep(3)
		self.assertEquals(len(results), 11,  "Expected %s results, but got %s" % (11, len(results)))
		time.sleep(3)
		self.assertEquals(len(results), 12,  "Expected %s results, but got %s" % (12, len(results)))
	
	#def test_poolDecorator(self):
	#	
	#	result = []
	#	
	#	def decoratorCallback(success, returned, errors):
	#		result.append(success)
	#		result.append(returned)
	#		result.append(errors)
        #
	#	#run class method in ThreadPool via decorator
	#	class SomeClass(object):
	#		@poolJob(callback=decoratorCallback)
	#		def poolJobTest(self):
	#			return "test"
	#	
	#	someClass = SomeClass()
	#	someClass.poolJobTest()
	#	
	#	#give job a second to finish
	#	time.sleep(1)
	#	
	#	self.assertTrue(result[0], "Expected callback success to be 'True', but got %s"%result[0])
	#	self.assertEqual(result[1], 'test', "Expected callback result to be 'test', but got %s"%result[1])
	#	self.assertIsNone(result[2], "Expected function to run successfully, but got error %s"% result[2])
		
	def tearDown(self):
		self.pool.stop()
	
