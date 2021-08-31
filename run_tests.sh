#! /bin/bash
[ -e coverage.xml ] && rm coverage.xml
set -e

py.test -v --log-level=WARNING \
	-o junit_family=xunit2 --junitxml=testreport-OPSI.xml \
	--cov-append --cov OPSI --cov-report term --cov-report xml \
	tests/testOpsi/test_backend_extend_d_70_dynamic_depot.py
	#tests/testOPSI
py.test -v --log-level=WARNING \
	-o junit_family=xunit2 --junitxml=testreport-opsicommon.xml \
	--cov-append --cov opsicommon --cov-report term --cov-report xml \
	tests/testopsicommon
