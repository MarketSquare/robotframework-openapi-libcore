*** Settings ***
Library     OpenApiLibCore
...         source=${origin}/openapi.json
...         origin=${origin}
...         base_path=${EMPTY}
...         mappings_path=${root}/tests/user_implemented/custom_user_mappings.py

*** Variables ***
${origin}=      http://localhost:8000

*** Test Cases ***
Test Authorized Request
    Authorized Request    url    method

Test Ensure In Use
    Ensure In Use    url    resource_relation

Test Get Ids For Endpoint
    Get Ids For Endpoint    url=${origin}/

Test Get Invalid Json Data
    Get Invalid Json Data    data_relations    schema    url    method    dto    status_code

Test Get Json Data For Dto Class
    Get Json Data For Dto Class    schema    dto_class    operation_id

Test Get Json Data With Conflict
    Get Json Data With Conflict    url    method    dto    conflict_status_code

Test Get Parameterized Endpoint From url
    Get Parameterized Endpoint From Url    url

Test Get Request Data
    Get Request Data    endpoint    method

Test Get Valid Id For Endpoint
    Get Valid Id For Endpoint    endpoint    method

Test Invalidate Parameters
    Invalidate Parameters    params    headers    relations    parameters    status_code
