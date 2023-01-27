*** Settings ***
Library         OpenApiLibCore
...                 source=${origin}/openapi.json
...                 origin=${origin}
...                 base_path=${EMPTY}
...                 mappings_path=${root}/tests/user_implemented/custom_user_mappings.py
...                 default_id_property_name=identification
Variables       ${root}/tests/variables.py


*** Variables ***
${origin}=      http://localhost:8000


*** Test Cases ***
Test Ensure In Use With Single Id In Url
    ${url}=    Get Valid Url    endpoint=/wagegroups/{wagegroup_id}    method=get
    Ensure In Use    url=${url}    resource_relation=${ID_REFERENCE}

# Test Ensure In Use With Multiple Ids In Url
#    ${url}=    Get Valid Url    endpoint=/wagegroups/{wagegroup_id}    method=get
#    Ensure In Use    url=${url}    resource_relation=${ID_REFERENCE}

Test Ensure In Use Raises When No Id In Url
    ${url}=    Get Valid Url    endpoint=/wagegroups    method=post
    Run Keyword And Expect Error    ValueError: The provided url*
    ...    Ensure In Use    url=${url}    resource_relation=${ID_REFERENCE}

Test Ensure In Use Raises When Post Fails
    ${url}=    Get Valid Url    endpoint=/wagegroups/{wagegroup_id}    method=get
    Run Keyword And Expect Error    HTTPError: 405 Client Error*
    ...    Ensure In Use    url=${url}    resource_relation=${INVALID_ID_REFERENCE}
