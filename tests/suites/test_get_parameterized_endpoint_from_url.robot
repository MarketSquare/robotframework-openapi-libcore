*** Settings ***
Library         OpenApiLibCore
...             source=${origin}/openapi.json
...             origin=${origin}
...             base_path=${EMPTY}
...             mappings_path=${root}/tests/user_implemented/custom_user_mappings.py
Variables       ${root}/tests/variables.py


*** Variables ***
${origin}=      http://localhost:8000


*** Test Cases ***
Test Get Parameterized Endpoint From Url Raises For Invalid Endpoint
    Run KeyWord And Expect Error    ValueError: /dummy not found in paths section of the OpenAPI document.
    ...    Get Parameterized Endpoint From Url    url=${origin}/dummy

Test Get Parameterized Endpoint From Url With No Id
    ${url}=    Get Valid Url    endpoint=/events/    method=get
    ${endpoint}=    Get Parameterized Endpoint From Url    url=${url}
    Should Be Equal    ${endpoint}    /events/

Test Get Parameterized Endpoint From Url With Single Id
    ${url}=    Get Valid Url    endpoint=/employees/{employee_id}    method=get
    ${endpoint}=    Get Parameterized Endpoint From Url    url=${url}
    Should Be Equal    ${endpoint}    /employees/{employee_id}

# Test Get Parameterized Endpoint From Url With Multiple Ids
#    ${url}=    Get Valid Url    endpoint=/events/    method=get
#    Get Parameterized Endpoint From Url    url=${url}
