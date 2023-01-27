*** Settings ***
Library         OpenApiLibCore
...                 source=${root}/tests/files/schema_with_allof.yaml
...                 origin=${origin}
...                 base_path=${EMPTY}
Variables       ${root}/tests/variables.py


*** Variables ***
${origin}=      http://localhost:8000


*** Test Cases ***
Test Get Request Data For Schema With allOf
    ${request_data}=    Get Request Data    endpoint=/hypermedia    method=post
    ${dict}=    Create Dictionary
    ${list}=    Create List
    ${list_of_dict}=    Create List    ${dict}
    Length Should Be    ${request_data.dto.isan}    36
    Length Should Be    ${request_data.dto.published}    10
    Should Be Equal    ${request_data.dto.tags}    ${list_of_dict}
    Length Should Be    ${request_data.dto_schema}    4
    Length Should Be    ${request_data.dto_schema.get("properties")}    4
    Should Be Equal    ${request_data.parameters}    ${list}
    Should Be Equal    ${request_data.params}    ${dict}
    Should Be Equal    ${request_data.headers}    ${dict}
