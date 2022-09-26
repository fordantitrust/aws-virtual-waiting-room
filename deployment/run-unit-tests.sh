#!/bin/bash
#
# This assumes all of the OS-level configuration has been completed and git repo has already been cloned
#
# This script should be run from the repo's deployment directory
# cd deployment
# ./run-unit-tests.sh
#

# Get reference for all important folders
template_dir="$PWD"
source_dir="$template_dir/../source"

echo "------------------------------------------------------------------------------"
echo " Test core API lambda functions"
echo "------------------------------------------------------------------------------"
cd $source_dir/core-api/lambda_functions
coverage run lambda_functions_tests.py
coverage xml
sed -i -- 's/filename\=\"/filename\=\"source\/core-api\/lambda_functions\//g' coverage.xml

echo "------------------------------------------------------------------------------"
echo " Test core API custom resources functions"
echo "------------------------------------------------------------------------------"
cd $source_dir/core-api/custom_resources
coverage run custom_resource_tests.py
coverage xml
sed -i -- 's/filename\=\"/filename\=\"source\/core-api\/custom_resources\//g' coverage.xml


echo "------------------------------------------------------------------------------"
echo " Test shared resources functions"
echo "------------------------------------------------------------------------------"
cd $source_dir/shared/
coverage run shared_resources_tests.py
coverage xml
sed -i -- 's/filename\=\"/filename\=\"source\/shared\//g' coverage.xml


echo "------------------------------------------------------------------------------"
echo " Test open-id waitingroom custom resources functions"
echo "------------------------------------------------------------------------------"
cd $source_dir/openid-waitingroom/custom_resources
coverage run custom_resources_tests.py
coverage xml
sed -i -- 's/filename\=\"/filename\=\"source\/openid-waitingroom\/custom_resources\//g' coverage.xml