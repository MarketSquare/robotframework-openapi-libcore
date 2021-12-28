*** Settings ***
Library         OpenApiLibCore
...             source=${origin}/openapi.json
...             origin=${origin}
...             base_path=${EMPTY}
...             mappings_path=${root}/tests/user_implemented/custom_user_mappings.py
Library         ../../.venv/lib/site-packages/robot/libraries/String.py
Variables       ${root}/tests/variables.py

*** Variables ***
${origin}=      http://localhost:8000

*** Test Cases ***
Test Get Invalidated Parameters Raises For Empty Params And Headers
    ${request_data}=    Get Request Data    endpoint=/employees    method=get
    ${dict}=    Create Dictionary
    Run Keyword And Expect Error    ValueError: No params or headers to invalidate.
    ...    Get Invalidated Parameters
    ...    status_code=422
    ...    request_data=${request_data}

Test Get Invalidated Parameters Raises For Empty Parameters List
    ${request_data}=    Get Request Data    endpoint=/secret_message    method=get
    Evaluate    ${request_data.parameters.clear()} is None
    Run Keyword And Expect Error    ValueError: Could not invalidate parameters: parameters list was empty.
    ...    Get Invalidated Parameters
    ...    status_code=422
    ...    request_data=${request_data}

Test Get Invalidated Parameters Raises For Mismatched Parameters List
    ${request_data}=    Get Request Data    endpoint=/secret_message    method=get
    Evaluate    ${request_data.parameters.clear()} is None
    Evaluate    ${request_data.parameters.append({"name": "dummy"})} is None
    Run Keyword And Expect Error    ValueError: secret-code not found in provided parameters.
    ...    Get Invalidated Parameters
    ...    status_code=422
    ...    request_data=${request_data}

    ${request_data}=    Get Request Data    endpoint=/secret_message    method=get
    Evaluate    ${request_data.parameters.clear()} is None
    Evaluate    ${request_data.parameters.append({"name": "dummy"})} is None
    Run Keyword And Expect Error    ValueError: secret-code from Relation not found in provided parameters.
    ...    Get Invalidated Parameters
    ...    status_code=401
    ...    request_data=${request_data}

Test Get Invalidated Parameters Raises For Status Code That Cannot Be Invalidated
    ${request_data}=    Get Request Data    endpoint=/secret_message    method=get
    Run Keyword And Expect Error    ValueError: No relations to cause status_code 200 found.
    ...    Get Invalidated Parameters
    ...    status_code=200
    ...    request_data=${request_data}

Test Get Invalidated Parameters For Invalid Propery Default Response
    ${request_data}=    Get Request Data    endpoint=/secret_message    method=get
    ${invalidated}=    Get Invalidated Parameters
    ...    status_code=422
    ...    request_data=${request_data}
    Set Test Variable    ${secret_code}    ${invalidated[1].get("secret-code")}
    Length Should Be    ${secret_code}    32

Test Get Invalidated Parameters For PropertyValueConstraint
    ${request_data}=    Get Request Data    endpoint=/secret_message    method=get
    ${invalidated}=    Get Invalidated Parameters
    ...    status_code=401
    ...    request_data=${request_data}
    Set Test Variable    ${secret_code}    ${invalidated[1].get("secret-code")}
    Should Be True    int($secret_code) != 42

Test Get Invalidated Parameters Params
    ${request_data}=    Get Request Data    endpoint=/energy_label/{zipcode}/{home_number}    method=get
    ${invalidated}=    Get Invalidated Parameters
    ...    status_code=422
    ...    request_data=${request_data}
    Set Test Variable    ${extension}    ${invalidated[0].get("extension")}
    Length Should Be    ${extension}    0
