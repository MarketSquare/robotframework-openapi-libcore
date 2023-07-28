*** Settings ***
Library         OpenApiLibCore
...                 source=${ROOT}/tests/files/schema_with_readOnly.json
...                 origin=${ORIGIN}
...                 base_path=${EMPTY}
...                 mappings_path=${ROOT}/tests/user_implemented/custom_user_mappings.py
Variables       ${ROOT}/tests/variables.py


*** Variables ***
${ORIGIN}=      http://localhost:8000


*** Test Cases ***
Test ReadOnly Is Filtered From Request Data
    ${request_data}=    Get Request Data    endpoint=/api/location    method=post
    ${json_data}=    Set Variable    ${request_data.dto.as_dict()}
    Should Not Contain    ${json_data}    id
    Should Contain    ${json_data}    locationId
    Should Contain    ${json_data}    timezone
