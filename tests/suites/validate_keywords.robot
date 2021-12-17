*** Settings ***
Library         OpenApiLibCore
...             source=${origin}/openapi.json
...             origin=${origin}
...             base_path=${EMPTY}
...             mappings_path=${root}/tests/user_implemented/custom_user_mappings.py
Library         ../../.venv/lib/site-packages/robot/libraries/Collections.py
Variables       ${root}/tests/variables.py

*** Variables ***
${origin}=      http://localhost:8000

*** Test Cases ***
Test Authorized Request
    ${response}=    Authorized Request    url=${origin}/    method=get
    Should Be Equal As Integers    ${response.status_code}    200

Test Get Valid Url
    ${url}=    Get Valid Url    endpoint=/wagegroups/{wagegroup_id}    method=delete
    Should Contain    container=${url}    item=${origin}/wagegroups/

    ${url}=    Get Valid Url    endpoint=/energy_label/{zipcode}/{home_number}    method=get
    Should Be Equal As Strings    ${url}    ${origin}/energy_label/1111AA/10

Test Ensure In Use
    ${url}=    Get Valid Url    endpoint=/wagegroups    method=post
    Ensure In Use    url=${url}    resource_relation=${ID_REFERENCE}

Test Get Ids For Endpoint
    # endpoint for a specific id
    ${url}=    Get Valid Url    endpoint=/wagegroups/{wagegroup_id}    method=post
    ${ids}=    Get Ids For Endpoint    url=${url}
    Length Should Be    item=${ids}    length=1

    # endpoint with a list of resources
    Get Valid Url    endpoint=/employees/{employee_id}    method=get
    ${url}=    Get Valid Url    endpoint=/employees    method=get
    ${ids}=    Get Ids For Endpoint    url=${url}
    ${number_of_ids}=    Get Length    item=${ids}
    Should Be True    $number_of_ids > 0

Test Get Invalid Json Data
    Run Keyword And Expect Error    Failed to invalidate*    Get Invalid Json Data
    ...    data_relations=[]
    ...    schema={}
    ...    url=none
    ...    method=none
    ...    dto=${DEFAULT_DTO}
    ...    status_code=999

    # no data_relations send, so invalidation is based on the schema
    ${request_data}=    Get Request Data    endpoint=/wagegroups    method=post
    ${invalid_json}=    Get Invalid Json Data
    ...    data_relations=[]
    ...    schema=${request_data.dto_schema}
    ...    url=none
    ...    method=none
    ...    dto=${request_data.dto}
    ...    status_code=422
    ${response}=    Authorized Request
    ...    url=${origin}/wagegroups    method=post    json_data=${invalid_json}
    Should Be Equal As Integers    ${response.status_code}    422

    # handle the UniquePropertyValueConstraint branch
    ${request_data}=    Get Request Data    endpoint=/wagegroups    method=post
    ${data_relations}=    Create List    ${request_data.dto.get_relations()}[0]
    ${invalid_json}=    Get Invalid Json Data
    ...    data_relations=${data_relations}
    ...    schema=${request_data.dto_schema}
    ...    url=${origin}/wagegroups
    ...    method=post
    ...    dto=${request_data.dto}
    ...    status_code=418
    ${response}=    Authorized Request
    ...    url=${origin}/wagegroups    method=post    json_data=${invalid_json}
    ${status_code}=    Evaluate    $response.status_code
    Should Be Equal As Integers    ${response.status_code}    418

    # handle the IdReference branch
    ${url}=    Get Valid Url    endpoint=/wagegroups/{wagegroup_id}    method=delete
    ${request_data}=    Get Request Data    endpoint=/wagegroups/{wagegroup_id}    method=delete
    ${data_relations}=    Create List    ${request_data.dto.get_relations()}[1]
    ${invalid_json}=    Get Invalid Json Data
    ...    data_relations=${data_relations}
    ...    schema=${request_data.dto_schema}
    ...    url=${url}
    ...    method=delete
    ...    dto=${request_data.dto}
    ...    status_code=406
    ${response}=    Authorized Request
    ...    url=${url}    method=delete    json_data=${invalid_json}
    Should Be Equal As Integers    ${response.status_code}    406

    # handle the other relations branch
    ${request_data}=    Get Request Data    endpoint=/wagegroups    method=post
    ${data_relations}=    Create List    ${PATH_CONSTRAINT}
    ${invalid_json}=    Get Invalid Json Data
    ...    data_relations=${data_relations}
    ...    schema=${request_data.dto_schema}
    ...    url=${origin}/wagegroups
    ...    method=post
    ...    dto=${request_data.dto}
    ...    status_code=422
    ${response}=    Authorized Request
    ...    url=${origin}/wagegroups    method=post    json_data=${invalid_json}
    Should Be Equal As Integers    ${response.status_code}    422

# Test Get Json Data For Dto Class
#    Get Json Data For Dto Class    schema    dto_class    operation_id

# Test Get Json Data With Conflict
#    Get Json Data With Conflict    url    method    dto    conflict_status_code

# Test Get Parameterized Endpoint From url
#    Get Parameterized Endpoint From Url    url

# Test Get Request Data
#    Get Request Data    endpoint    method

# Test Get Valid Id For Endpoint
#    Get Valid Id For Endpoint    endpoint    method

# Test Invalidate Parameters
#    Invalidate Parameters    params    headers    relations    parameters    status_code
