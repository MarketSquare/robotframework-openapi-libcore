# region: docstring
"""
# OpenApiLibCore for Robot Framework®

The OpenApiLibCore library is a utility library that is meant to simplify creation
of other Robot Framework libraries for API testing based on the information in
an OpenAPI document (also known as Swagger document).
This document explains how to use the OpenApiLibCore library.

For more information about Robot Framework®, see http://robotframework.org.

---

> Note: OpenApiLibCore is still being developed so there are currently
restrictions / limitations that you may encounter when using this library to run
tests against an API. See [Limitations](#limitations) for details.

---

## Installation

If you already have Python >= 3.8 with pip installed, you can simply run:

`pip install --upgrade robotframework-openapi-libcore`

---

## OpenAPI (aka Swagger)

The OpenAPI Specification (OAS) defines a standard, language-agnostic interface
to RESTful APIs, see https://swagger.io/specification/

The OpenApiLibCore implements a number of Robot Framework keywords that make it
easy to interact with an OpenAPI implementation by using the information in the
openapi document (Swagger file), for examply by automatic generation of valid values
for requests based on the schema information in the document.

> Note: OpenApiLibCore is designed for APIs based on the OAS v3
The library has not been tested for APIs based on the OAS v2.

---

## Getting started

Before trying to use the keywords exposed by OpenApiLibCore on the target API
it's recommended to first ensure that the openapi document for the API is valid
under the OpenAPI Specification.

This can be done using the command line interface of a package that is installed as
a prerequisite for OpenApiLibCore.
Both a local openapi.json or openapi.yaml file or one hosted by the API server
can be checked using the `prance validate <reference_to_file>` shell command:

```shell
prance validate http://localhost:8000/openapi.json
Processing "http://localhost:8000/openapi.json"...
 -> Resolving external references.
Validates OK as OpenAPI 3.0.2!

prance validate /tests/files/petstore_openapi.yaml
Processing "/tests/files/petstore_openapi.yaml"...
 -> Resolving external references.
Validates OK as OpenAPI 3.0.2!
```

You'll have to change the url or file reference to the location of the openapi
document for your API.

> Note: if you encounter a `Recursion reached limit ...` error there is a circular
reference somewhere in your OpenAPI document.
Although recursion is technically allowed under the OAS, tool support is limited
and changing the API to not use recursion is recommended.
At present OpenApiLibCore does not support recursion in the OpenAPI document.

If the openapi document passes this validation, the next step is trying to do a test
run with a minimal test suite.
The example below can be used, with `source`, `origin` and 'endpoint' altered to
fit your situation.

``` robotframework
*** Settings ***
Library            OpenApiLibCore
...                    source=http://localhost:8000/openapi.json
...                    origin=http://localhost:8000

*** Test Cases ***
Getting Started
    ${url}=    Get Valid Url    endpoint=/employees/{employee_id}   method=get

```

Running the above suite for the first time may result in an error / failed test.
You should look at the Robot Framework `log.html` to determine the reasons
for the failing tests.
Depending on the reasons for the failures, different solutions are possible.

Details about the OpenApiLibCore library parameters and keywords that you may need can be found
[here](https://marketsquare.github.io/robotframework-openapi-libcore/openapi_libcore.html).

The OpenApiLibCore also support handling of relations between resources within the scope
of the API being validated as well as handling dependencies on resources outside the
scope of the API. In addition there is support for handling restrictions on the values
of parameters and properties.

Details about the `mappings_path` variable usage can be found
[here](https://marketsquare.github.io/robotframework-openapi-libcore/advanced_use.html).

---

## Limitations

There are currently a number of limitations to supported API structures, supported
data types and properties. The following list details the most important ones:
- Only JSON request and response bodies are currently supported.
- The unique identifier for a resource as used in the `paths` section of the
    openapi document is expected to be the `id` property on a resource of that type.
- Limited support for query strings and headers.
- Limited support for authentication
    - `username` and `password` can be passed as parameters to use Basic Authentication
    - A [requests AuthBase instance](https://docs.python-requests.org/en/latest/api/#authentication)
        can be passed and it will be used as provided.
    - No support for per-endpoint authorization levels (just simple 401 validation).
- byte, binary, date, date-time string formats not supported yet.

"""
# endregion

import json as _json
import sys
from copy import deepcopy
from dataclasses import Field, asdict, dataclass, field, make_dataclass
from functools import cached_property
from itertools import zip_longest
from logging import getLogger
from pathlib import Path
from random import choice
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union
from uuid import uuid4

from openapi_core import create_spec
from openapi_core.validation.response.validators import ResponseValidator
from prance import ResolvingParser
from prance.util.url import ResolutionError
from requests import Response, Session
from requests.auth import AuthBase, HTTPBasicAuth
from robot.api.deco import keyword, library
from robot.libraries.BuiltIn import BuiltIn

from OpenApiLibCore import value_utils
from OpenApiLibCore.dto_base import (
    Dto,
    IdDependency,
    IdReference,
    PathPropertiesConstraint,
    PropertyValueConstraint,
    Relation,
    UniquePropertyValueConstraint,
)
from OpenApiLibCore.dto_utils import DefaultDto, get_dto_class
from OpenApiLibCore.value_utils import IGNORE

run_keyword = BuiltIn().run_keyword


logger = getLogger(__name__)


# TODO: figure out if oneOf and anyOf need special handling
def resolve_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Helper method to resolve allOf instances in a schema."""
    # schema is mutable, so deepcopy to prevent mutation of original schema argument
    resolved_schema: Dict[str, Any] = deepcopy(schema)
    if schema_parts := resolved_schema.pop("allOf", None):
        for schema_part in schema_parts:
            resolved_part = resolve_schema(schema_part)
            resolved_schema = merge_schemas(resolved_schema, resolved_part)
    return resolved_schema


def merge_schemas(first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
    """Helper method to merge two schemas, recursively."""
    merged_schema = deepcopy(first)
    for key, value in second.items():
        # for existing keys, merge dict and list values, leave others unchanged
        if key in merged_schema.keys():
            if isinstance(value, dict):
                # if the key holds a dict, merge the values (e.g. 'properties')
                merged_schema[key].update(value)
            elif isinstance(value, list):
                # if the key holds a list, extend the values (e.g. 'required')
                merged_schema[key].extend(value)
            else:
                logger.debug(
                    f"key '{key}' with value '{merged_schema[key]}' not "
                    f"updated to '{value}'"
                )
        else:
            merged_schema[key] = value
    return merged_schema


@dataclass
class RequestValues:
    """Helper class to hold parameter values needed to make a request."""

    url: str
    method: str
    params: Optional[Dict[str, Any]]
    headers: Optional[Dict[str, str]]
    json_data: Optional[Dict[str, Any]]


@dataclass
class RequestData:
    """Helper class to manage parameters used when making requests."""

    dto: Union[Dto, DefaultDto] = DefaultDto()
    dto_schema: Dict[str, Any] = field(default_factory=dict)
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # prevent modification by reference
        self.dto_schema = deepcopy(self.dto_schema)
        self.parameters = deepcopy(self.parameters)
        self.params = deepcopy(self.params)
        self.headers = deepcopy(self.headers)

    @property
    def has_optional_properties(self) -> bool:
        """Whether or not the dto data (json data) contains optional properties."""
        properties = asdict(self.dto).keys()
        in_required_func: Callable[[str], bool] = lambda x: x in self.dto_schema.get(
            "required", []
        )
        return not all(map(in_required_func, properties))

    @property
    def has_optional_params(self) -> bool:
        """Whether or not any of the query parameters are optional."""
        optional_params = [
            p.get("name")
            for p in self.parameters
            if p.get("in") == "query" and not p.get("required")
        ]
        in_optional_params: Callable[[str], bool] = lambda x: x in optional_params
        return any(map(in_optional_params, self.params))

    @property
    def has_optional_headers(self) -> bool:
        """Whether or not any of the headers are optional."""
        optional_headers = [
            p.get("name")
            for p in self.parameters
            if p.get("in") == "header" and not p.get("required")
        ]
        in_optional_headers: Callable[[str], bool] = lambda x: x in optional_headers
        return any(map(in_optional_headers, self.headers))

    @cached_property
    def headers_that_can_be_invalidated(self) -> Set[str]:
        """
        The header parameters that can be invalidated by violating data
        restrictions or by not providing them in a request.
        """
        result = set()
        headers = [h for h in self.parameters if h.get("in") == "header"]
        for header in headers:
            schema: Dict[str, Any] = header["schema"]
            if set(schema.keys()).intersection(
                {
                    "enum",
                    "minimum",
                    "maximum",
                    "exclusiveMinimum",
                    "exclusiveMaximum",
                    "minLength",
                    "maxLength",
                    "minItems",
                    "maxItems",
                }
            ):
                result.add(header["name"])
            if header["required"]:
                result.add(header["name"])
        return result

    def get_required_properties_dict(self) -> Dict[str, Any]:
        """Get the json-compatible dto data containing only the required properties."""
        required_properties = self.dto_schema.get("required", [])
        required_properties_dict: Dict[str, Any] = {}
        for key, value in asdict(self.dto).items():
            if key in required_properties:
                required_properties_dict[key] = value
        return required_properties_dict

    def get_required_params(self) -> Dict[str, str]:
        """Get the params dict containing only the required query parameters."""
        required_parameters = [
            p.get("name") for p in self.parameters if p.get("required")
        ]
        return {k: v for k, v in self.params.items() if k in required_parameters}

    def get_required_headers(self) -> Dict[str, str]:
        """Get the headers dict containing only the required headers."""
        required_parameters = [
            p.get("name") for p in self.parameters if p.get("required")
        ]
        return {k: v for k, v in self.headers.items() if k in required_parameters}


@library(scope="TEST SUITE", doc_format="ROBOT")
class OpenApiLibCore:  # pylint: disable=too-many-instance-attributes
    """
    Main class providing the keywords and core logic to interact with an OpenAPI server.

    Visit the [https://github.com/MarketSquare/robotframework-openapi-libcore | library page]
    for an introduction.
    """

    def __init__(  # pylint: disable=too-many-arguments, too-many-locals
        self,
        source: str,
        origin: str = "",
        base_path: str = "",
        mappings_path: Union[str, Path] = "",
        username: str = "",
        password: str = "",
        security_token: str = "",
        auth: Optional[AuthBase] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        invalid_property_default_response: int = 422,
    ) -> None:
        # region: docstring
        """
        === source ===
        An absolute path to an openapi.json or openapi.yaml file or an url to such a file.

        === origin ===
        The server (and port) of the target server. E.g. ``https://localhost:7000``

        === base_path ===
        The routing between ``origin`` and the endpoints as found in the ``paths`` in the
        openapi document. E.g. ``/petshop/v2``.

        === mappings_path ===
        See [https://marketsquare.github.io/robotframework-openapi-libcore/advanced_use.html | here].

        === username ===
        The username to be used for Basic Authentication.

        === password ===
        The password to be used for Basic Authentication.

        === security_token ===
        The token to be used for token based security using the ``Authorization`` header.

        === auth ===
        A [https://docs.python-requests.org/en/latest/api/#authentication | requests AuthBase instance]
        to be used for authentication instead of the ``username`` and ``password``.

        === extra_headers ===
        A dictionary with extra / custom headers that will be send with every request.
        This parameter can be used to send headers that are not documented in the
        openapi document or to provide an API-key.

        === invalid_property_default_response ===
        The default response code for requests with a JSON body that does not comply with
        the schema. Example: a value outside the specified range or a string value for a
        property defined as integer in the schema.
        """
        # endregion
        try:
            parser = ResolvingParser(source, backend="openapi-spec-validator")
        except ResolutionError as exception:
            BuiltIn().fatal_error(
                f"Exception while trying to load openapi spec from source: {exception}"
            )
        if (openapi_spec := parser.specification) is None:  # pragma: no cover
            BuiltIn().fatal_error(
                "Source was loaded, but no specification was present after parsing."
            )
        self._openapi_spec: Dict[str, Any] = openapi_spec
        validation_spec = create_spec(self.openapi_spec)
        self.response_validator = ResponseValidator(
            spec=validation_spec,
            base_url=base_path,
        )
        self.session = Session()
        self.origin = origin
        self.base_url = f"{self.origin}{base_path}"
        # only username and password, security_token or auth object should be provided
        # if multiple are provided, username and password take precedence
        self.security_token = security_token
        self.auth = auth
        if username and password:
            self.auth = HTTPBasicAuth(username, password)
        self.extra_headers = extra_headers
        self.invalid_property_default_response = invalid_property_default_response
        if mappings_path and str(mappings_path) != ".":
            mappings_path = Path(mappings_path)
            if not mappings_path.is_file():
                logger.warning(
                    f"mappings_path '{mappings_path}' is not a Python module."
                )
            # intermediate variable to ensure path.append is possible so we'll never
            # path.pop a location that we didn't append
            mappings_folder = str(mappings_path.parent)
            sys.path.append(mappings_folder)
            mappings_module_name = mappings_path.stem
            self.get_dto_class = get_dto_class(
                mappings_module_name=mappings_module_name
            )
            sys.path.pop()
        else:
            self.get_dto_class = get_dto_class(mappings_module_name="no_mapping")

    @property
    def openapi_spec(self):
        """Return a deepcopy of the parsed openapi document."""
        # protect the parsed openapi spec from being mutated by reference
        return deepcopy(self._openapi_spec)

    @keyword
    def get_valid_url(self, endpoint: str, method: str) -> str:
        """
        This keyword returns a valid url for the given `endpoint` and `method`.

        If the `endpoint` contains path parameters the Get Valid Id For Endpoint
        keyword will be executed to retrieve valid ids for the path parameters.

        > Note: if valid ids cannot be retrieved within the scope of the API, the
        `PathPropertiesConstraint` Relation can be used. More information can be found
        [https://marketsquare.github.io/robotframework-openapi-libcore/advanced_use.html | here].
        """
        method = method.lower()
        try:
            self.openapi_spec["paths"][endpoint]
        except KeyError:
            raise ValueError(
                f"{endpoint} not found in paths section of the OpenAPI document."
            ) from None
        dto_class = self.get_dto_class(endpoint=endpoint, method=method)
        relations = dto_class.get_relations()
        paths = [p.path for p in relations if isinstance(p, PathPropertiesConstraint)]
        if paths:
            url = f"{self.base_url}{choice(paths)}"
            return url
        endpoint_parts = list(endpoint.split("/"))
        for index, part in enumerate(endpoint_parts):
            if part.startswith("{") and part.endswith("}"):
                type_endpoint_parts = endpoint_parts[slice(index)]
                type_endpoint = "/".join(type_endpoint_parts)
                existing_id: str = run_keyword(
                    "get_valid_id_for_endpoint", type_endpoint, method
                )
                endpoint_parts[index] = existing_id
        resolved_endpoint = "/".join(endpoint_parts)
        url = f"{self.base_url}{resolved_endpoint}"
        return url

    @keyword
    def get_valid_id_for_endpoint(self, endpoint: str, method: str) -> str:
        """
        Support keyword that returns the `id` for an existing resource at `endpoint`.

        To prevent resource conflicts with other test cases, a new resource is created
        (POST) if possible.
        """
        method = method.lower()
        url: str = run_keyword("get_valid_url", endpoint, method)
        # Try to create a new resource to prevent conflicts caused by
        # operations performed on the same resource by other test cases
        request_data = self.get_request_data(endpoint=endpoint, method="post")

        response: Response = run_keyword(
            "authorized_request",
            url,
            "post",
            request_data.get_required_params(),
            request_data.get_required_headers(),
            request_data.get_required_properties_dict(),
        )
        if response.status_code == 405:
            # For endpoints that do no support POST, try to get an existing id using GET
            try:
                valid_id = choice(run_keyword("get_ids_from_url", url))
                return valid_id
            except Exception as exception:
                raise AssertionError(
                    f"Failed to get a valid id using GET on {url}"
                ) from exception

        assert (
            response.ok
        ), f"get_valid_id_for_endpoint received status_code {response.status_code}"
        response_data = response.json()
        if prepared_body := response.request.body:
            if isinstance(prepared_body, bytes):
                send_json = _json.loads(prepared_body.decode("UTF-8"))
            else:
                send_json = _json.loads(prepared_body)
        else:
            send_json = None
        # no support for retrieving an id from an array returned on a POST request
        if isinstance(response_data, list):
            raise NotImplementedError(
                f"Unexpected response body for POST request: expected an object but "
                f"received an array ({response_data})"
            )
        # POST on /resource_type/{id}/array_item/ will return the updated {id} resource
        # instead of a newly created resource. In this case, the send_json must be
        # in the array of the 'array_item' property on {id}
        send_path: str = response.request.path_url
        response_path: Optional[str] = response_data.get("href", None)
        if response_path and (send_path not in response_path) and send_json:
            try:
                property_to_check = send_path.replace(response_path, "")[1:]
                item_list: List[Dict[str, Any]] = response_data[property_to_check]
                # Use the (mandatory) id to get the POSTed resource from the list
                [valid_id] = [
                    item["id"] for item in item_list if item["id"] == send_json["id"]
                ]
            except Exception as exception:
                raise AssertionError(
                    f"Failed to get a valid id from {response_path}"
                ) from exception
        else:
            try:
                valid_id = response_data["id"]
            except KeyError:
                raise AssertionError(
                    f"Failed to get a valid id from {response_data}"
                ) from None
        return valid_id

    @keyword
    def get_ids_from_url(self, url: str) -> List[str]:
        """
        Perform a GET request on the `url` and return the list of resource
        `ids` from the response.
        """
        endpoint = self.get_parameterized_endpoint_from_url(url)
        request_data = self.get_request_data(endpoint=endpoint, method="get")
        response = run_keyword(
            "authorized_request",
            url,
            "get",
            request_data.get_required_params(),
            request_data.get_required_headers(),
        )
        assert response.ok
        response_data: Union[Dict[str, Any], List[Dict[str, Any]]] = response.json()
        if isinstance(response_data, list):
            valid_ids: List[str] = [item["id"] for item in response_data]
            return valid_ids
        if valid_id := response_data.get("id"):
            return [valid_id]
        valid_ids = [item["id"] for item in response_data["items"]]
        return valid_ids

    @keyword
    def get_request_data(self, endpoint: str, method: str) -> RequestData:
        """Return an object with valid request data for body, headers and query params."""
        method = method.lower()
        # The endpoint can contain already resolved Ids that have to be matched
        # against the parametrized endpoints in the paths section.
        spec_endpoint = self.get_parametrized_endpoint(endpoint)
        dto_class = self.get_dto_class(endpoint=spec_endpoint, method=method)
        try:
            method_spec = self.openapi_spec["paths"][spec_endpoint][method]
        except KeyError:
            logger.warning(
                f"method '{method}' not supported on '{spec_endpoint}, using empty spec."
            )
            method_spec = {}

        parameters, params, headers = self.get_request_parameters(
            dto_class=dto_class, method_spec=method_spec
        )
        if (body_spec := method_spec.get("requestBody", None)) is None:
            if dto_class == DefaultDto:
                dto_instance: Dto = DefaultDto()
            else:
                dto_class = make_dataclass(
                    cls_name=method_spec["operationId"],
                    fields=[],
                    bases=(dto_class,),
                )
                dto_instance = dto_class()
            return RequestData(
                dto=dto_instance,
                parameters=parameters,
                params=params,
                headers=headers,
            )
        content_schema = self.get_content_schema(body_spec)
        dto_data = self.get_json_data_for_dto_class(
            schema=content_schema,
            dto_class=dto_class,
            operation_id=method_spec.get("operationId"),
        )
        if dto_data is None:
            dto_instance = DefaultDto()
        else:
            fields = self.get_fields_from_dto_data(content_schema, dto_data)
            dto_class = make_dataclass(
                cls_name=method_spec["operationId"],
                fields=fields,
                bases=(dto_class,),
            )
            dto_instance = dto_class(**dto_data)  # type: ignore[call-arg]
        return RequestData(
            dto=dto_instance,
            dto_schema=content_schema,
            parameters=parameters,
            params=params,
            headers=headers,
        )

    @staticmethod
    def get_fields_from_dto_data(
        content_schema: Dict[str, Any], dto_data: Dict[str, Any]
    ):
        """Get a dataclasses fields list based on the content_schema and dto_data."""
        fields: List[Union[str, Tuple[str, type], Tuple[str, type, Field[Any]]]] = []
        for key, value in dto_data.items():
            required_properties = content_schema.get("required", [])
            if key in required_properties:
                fields.append((key, type(value)))
            else:
                fields.append((key, type(value), field(default=None)))  # type: ignore[arg-type]
        return fields

    def get_request_parameters(
        self, dto_class: Union[Dto, Type[Dto]], method_spec: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, str]]:
        """Get the methods parameter spec and params and headers with valid data."""
        parameters = method_spec.get("parameters", [])
        parameter_relations = dto_class.get_parameter_relations()
        query_params = [p for p in parameters if p.get("in") == "query"]
        header_params = [p for p in parameters if p.get("in") == "header"]
        params = self.get_parameter_data(query_params, parameter_relations)
        headers = self.get_parameter_data(header_params, parameter_relations)
        return parameters, params, headers

    @staticmethod
    def get_content_schema(body_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Get the content schema from the requestBody spec."""
        # Content should be a single key/value entry, so use tuple assignment
        (content_type,) = body_spec["content"].keys()
        if content_type != "application/json":
            # At present no supported for other types.
            raise NotImplementedError(f"content_type '{content_type}' not supported")
        content_schema = body_spec["content"][content_type]["schema"]
        resolved_schema: Dict[str, Any] = resolve_schema(content_schema)
        return resolved_schema

    def get_parametrized_endpoint(self, endpoint: str) -> str:
        """
        Get the parametrized endpoint as found in the `paths` section of the openapi
        document from a (partially) resolved endpoint.
        """

        def match_parts(parts: List[str], spec_parts: List[str]) -> bool:
            for part, spec_part in zip_longest(parts, spec_parts, fillvalue="Filler"):
                if part == "Filler" or spec_part == "Filler":
                    return False
                if part != spec_part and not spec_part.startswith("{"):
                    return False
            return True

        endpoint_parts = endpoint.split("/")
        spec_endpoints: List[str] = {**self.openapi_spec}["paths"].keys()
        for spec_endpoint in spec_endpoints:
            spec_endpoint_parts = spec_endpoint.split("/")
            if match_parts(endpoint_parts, spec_endpoint_parts):
                return spec_endpoint
        raise ValueError(
            f"{endpoint} not found in paths section of the OpenAPI document."
        )

    @staticmethod
    def get_parameter_data(
        parameters: List[Dict[str, Any]],
        parameter_relations: List[Relation],
    ) -> Dict[str, str]:
        """Generate a valid list of key-value pairs for all parameters."""
        result: Dict[str, str] = {}
        value: Any = None
        for parameter in parameters:
            parameter_name = parameter["name"]
            parameter_schema = parameter["schema"]
            relations = [
                r for r in parameter_relations if r.property_name == parameter_name
            ]
            if constrained_values := [
                r.values for r in relations if isinstance(r, PropertyValueConstraint)
            ]:
                value = choice(*constrained_values)
                if value is IGNORE:
                    continue
                result[parameter_name] = str(value)
                continue
            value = value_utils.get_valid_value(parameter_schema)
            # By the http standard, query string and header values must be strings
            result[parameter_name] = str(value)
        return result

    @keyword
    def get_json_data_for_dto_class(
        self,
        schema: Dict[str, Any],
        dto_class: Union[Dto, Type[Dto]],
        operation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a valid (json-compatible) dict for all the `dto_class` properties.
        """

        def get_constrained_values(property_name: str) -> List[Any]:
            relations = dto_class.get_relations()
            values_list = [
                c.values
                for c in relations
                if (
                    isinstance(c, PropertyValueConstraint)
                    and c.property_name == property_name
                )
            ]
            # values should be empty or contain 1 list of allowed values
            return values_list.pop() if values_list else []

        def get_dependent_id(property_name: str, operation_id: str) -> Optional[str]:
            relations = dto_class.get_relations()
            # multiple get paths are possible based on the operation being performed
            id_get_paths = [
                (d.get_path, d.operation_id)
                for d in relations
                if (isinstance(d, IdDependency) and d.property_name == property_name)
            ]
            if not id_get_paths:
                return None
            if len(id_get_paths) == 1:
                id_get_path, _ = id_get_paths.pop()
            else:
                try:
                    [id_get_path] = [
                        path
                        for path, operation in id_get_paths
                        if operation == operation_id
                    ]
                # There could be multiple get_paths, but not one for the current operation
                except ValueError:
                    return None
            valid_id = self.get_valid_id_for_endpoint(
                endpoint=id_get_path, method="get"
            )
            logger.debug(f"get_dependent_id for {id_get_path} returned {valid_id}")
            return valid_id

        json_data: Dict[str, Any] = {}

        for property_name in schema.get("properties", []):
            value_schema = schema["properties"][property_name]
            property_type = value_schema["type"]
            if constrained_values := get_constrained_values(property_name):
                # do not add properties that are configured to be ignored
                if IGNORE in constrained_values:
                    continue
                json_data[property_name] = choice(constrained_values)
                continue
            if dependent_id := get_dependent_id(
                property_name=property_name, operation_id=operation_id
            ):
                json_data[property_name] = dependent_id
                continue
            if property_type == "object":
                object_data = self.get_json_data_for_dto_class(
                    schema=value_schema,
                    dto_class=DefaultDto,
                    operation_id="",
                )
                json_data[property_name] = object_data
                continue
            if property_type == "array":
                array_data = self.get_json_data_for_dto_class(
                    schema=value_schema["items"],
                    dto_class=DefaultDto,
                    operation_id=operation_id,
                )
                json_data[property_name] = [array_data]
                continue
            json_data[property_name] = value_utils.get_valid_value(value_schema)
        return json_data

    @keyword
    def get_invalidated_url(self, valid_url: str) -> Optional[str]:
        """
        Return an url with all the path parameters in the `valid_url` replaced by a
        random UUID.

        Raises ValueError if the valid_url cannot be invalidated.
        """
        parameterized_endpoint = self.get_parameterized_endpoint_from_url(valid_url)
        parameterized_url = self.base_url + parameterized_endpoint
        valid_url_parts = list(reversed(valid_url.split("/")))
        parameterized_parts = reversed(parameterized_url.split("/"))
        for index, (parameterized_part, _) in enumerate(
            zip(parameterized_parts, valid_url_parts)
        ):
            if parameterized_part.startswith("{") and parameterized_part.endswith("}"):
                valid_url_parts[index] = uuid4().hex
                valid_url_parts.reverse()
                invalid_url = "/".join(valid_url_parts)
                return invalid_url
        raise ValueError(f"{parameterized_endpoint} could not be invalidated.")

    @keyword
    def get_parameterized_endpoint_from_url(self, url: str):
        """
        Return the endpoint as found in the `paths` section based on the given `url`.
        """
        endpoint = url.replace(self.base_url, "")
        endpoint_parts = endpoint.split("/")
        # first part will be '' since an endpoint starts with /
        endpoint_parts.pop(0)
        parameterized_endpoint = self.get_parametrized_endpoint(endpoint=endpoint)
        return parameterized_endpoint

    @keyword
    def get_invalid_json_data(
        self,
        url: str,
        method: str,
        status_code: int,
        request_data: RequestData,
    ) -> Dict[str, Any]:
        """
        Return `json_data` based on the `dto` on the `request_data` that will cause
        the provided `status_code` for the `method` operation on the `url`.

        > Note: applicable UniquePropertyValueConstraint and IdReference Relations are
            considered before changes to `json_data` are made.
        """
        method = method.lower()
        data_relations = request_data.dto.get_relations_for_error_code(status_code)
        if not data_relations:
            if not request_data.dto_schema:
                raise ValueError(
                    "Failed to invalidate: no data_relations and empty schema."
                )
            json_data = request_data.dto.get_invalidated_data(
                schema=request_data.dto_schema,
                status_code=status_code,
                invalid_property_default_code=self.invalid_property_default_response,
            )
            return json_data
        resource_relation = choice(data_relations)
        if isinstance(resource_relation, UniquePropertyValueConstraint):
            json_data = run_keyword(
                "get_json_data_with_conflict",
                url,
                method,
                request_data.dto,
                status_code,
            )
        elif isinstance(resource_relation, IdReference):
            run_keyword("ensure_in_use", url, resource_relation)
            json_data = asdict(request_data.dto)
        else:
            json_data = request_data.dto.get_invalidated_data(
                schema=request_data.dto_schema,
                status_code=status_code,
                invalid_property_default_code=self.invalid_property_default_response,
            )
        return json_data

    @keyword
    def get_invalidated_parameters(
        self,
        status_code: int,
        request_data: RequestData,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Returns a version of `params, headers` as present on `request_data` that has
        been modified to cause the provided `status_code`.
        """
        if not request_data.parameters:
            raise ValueError("No params or headers to invalidate.")
        # ensure the status_code can be triggered
        relations = request_data.dto.get_parameter_relations_for_error_code(status_code)
        relations_for_status_code = [
            r
            for r in relations
            if isinstance(r, PropertyValueConstraint) and r.error_code == status_code
        ]
        relation_property_names = {r.property_name for r in relations_for_status_code}
        if not relation_property_names:
            if status_code != self.invalid_property_default_response:
                raise ValueError(
                    f"No relations to cause status_code {status_code} found."
                )
        # ensure we're not modifying mutable properties
        params = deepcopy(request_data.params)
        headers = deepcopy(request_data.headers)

        if status_code == self.invalid_property_default_response:
            parameter_names = set(params.keys()).union(
                request_data.headers_that_can_be_invalidated
            )
            parameter_names.update(relation_property_names)
            # if all parameters are optional and none were provided, randomly pick one
            if not parameter_names:
                parameter_names = {
                    d["name"] for d in request_data.parameters if d["in"] in ["query"]
                }
            if not parameter_names:
                raise ValueError("Headers cannot be invalidated.")
        else:
            # non-default status_codes can only be the result of a Relation
            parameter_names = relation_property_names

        parameter_to_invalidate = choice(tuple(parameter_names))
        # check for invalid parameters in the provided request_data
        try:
            [parameter_data] = [
                data
                for data in request_data.parameters
                if data["name"] == parameter_to_invalidate
            ]
        except Exception:
            raise ValueError(
                f"{parameter_to_invalidate} not found in provided parameters."
            ) from None
        # get the constraint values if available for the chosen parameter
        try:
            [values_from_constraint] = [
                r.values
                for r in relations_for_status_code
                if r.property_name == parameter_to_invalidate
            ]
        except ValueError:
            values_from_constraint = []
        # if the parameter was not provided, add it to params / headers
        params, headers = self.ensure_parameter_in_parameters(
            parameter_to_invalidate=parameter_to_invalidate,
            params=params,
            headers=headers,
            parameter_data=parameter_data,
            values_from_constraint=values_from_constraint,
        )
        # determine the invalid_value
        if parameter_to_invalidate in params.keys():
            valid_value = params[parameter_to_invalidate]
        else:
            valid_value = headers[parameter_to_invalidate]

        invalid_value = value_utils.get_invalid_value(
            value_schema=parameter_data["schema"],
            current_value=valid_value,
            values_from_constraint=values_from_constraint,
        )
        # update the params / headers and return
        if parameter_to_invalidate in params.keys():
            params[parameter_to_invalidate] = invalid_value
        else:
            headers[parameter_to_invalidate] = str(invalid_value)
        return params, headers

    @staticmethod
    def ensure_parameter_in_parameters(
        parameter_to_invalidate: str,
        params: Dict[str, Any],
        headers: Dict[str, str],
        parameter_data: Dict[str, Any],
        values_from_constraint: List[Any],
    ):
        """
        Returns the params, headers tuple with parameter_to_invalidate with a valid
        value to params or headers if not originally present.
        """
        if (
            parameter_to_invalidate not in params.keys()
            and parameter_to_invalidate not in headers.keys()
        ):
            if values_from_constraint:
                valid_value = choice(values_from_constraint)
            else:
                valid_value = value_utils.get_valid_value(parameter_data["schema"])
            if (
                parameter_data["in"] == "query"
                and parameter_to_invalidate not in params.keys()
            ):
                params[parameter_to_invalidate] = valid_value
            if (
                parameter_data["in"] == "header"
                and parameter_to_invalidate not in headers.keys()
            ):
                headers[parameter_to_invalidate] = valid_value
        return params, headers

    @keyword
    def ensure_in_use(self, url: str, resource_relation: IdReference) -> None:
        """
        Ensure that the (right-most) `id` of the resource referenced by the `url`
        is used by the resource defined by the `resource_relation`.
        """
        resource_id = ""

        endpoint = url.replace(self.base_url, "")
        endpoint_parts = endpoint.split("/")
        parameterized_endpoint = self.get_parametrized_endpoint(endpoint=endpoint)
        parameterized_endpoint_parts = parameterized_endpoint.split("/")
        for part, param_part in zip(
            reversed(endpoint_parts), reversed(parameterized_endpoint_parts)
        ):
            if param_part.endswith("}"):
                resource_id = part
                break
        if not resource_id:
            raise ValueError(f"The provided url ({url}) does not contain an id.")
        request_data = self.get_request_data(
            method="post", endpoint=resource_relation.post_path
        )
        json_data = asdict(request_data.dto)
        json_data[resource_relation.property_name] = resource_id
        post_url: str = run_keyword(
            "get_valid_url",
            resource_relation.post_path,
            "post",
        )
        response: Response = run_keyword(
            "authorized_request",
            post_url,
            "post",
            request_data.params,
            request_data.headers,
            json_data,
        )
        if not response.ok:
            logger.debug(
                f"POST on {post_url} with json {json_data} failed: {response.json()}"
            )
            response.raise_for_status()

    @keyword
    def get_json_data_with_conflict(
        self, url: str, method: str, dto: Dto, conflict_status_code: int
    ) -> Dict[str, Any]:
        """
        Return `json_data` based on the `UniquePropertyValueConstraint` that must be
        returned by the `get_relations` implementation on the `dto` for the given
        `conflict_status_code`.
        """
        method = method.lower()
        json_data = asdict(dto)
        unique_property_value_constraints = [
            r
            for r in dto.get_relations()
            if isinstance(r, UniquePropertyValueConstraint)
        ]
        for relation in unique_property_value_constraints:
            json_data[relation.property_name] = relation.value
            # create a new resource that the original request will conflict with
            if method in ["patch", "put"]:
                post_url_parts = url.split("/")[:-1]
                post_url = "/".join(post_url_parts)
                # the PATCH or PUT may use a different dto than required for POST
                # so a valid POST dto must be constructed
                endpoint = post_url.replace(self.base_url, "")
                request_data = self.get_request_data(endpoint=endpoint, method="post")
                post_json = asdict(request_data.dto)
                for key in post_json.keys():
                    if key in json_data:
                        post_json[key] = json_data.get(key)
            else:
                post_url = url
                post_json = json_data
            endpoint = post_url.replace(self.base_url, "")
            request_data = self.get_request_data(endpoint=endpoint, method="post")
            response: Response = run_keyword(
                "authorized_request",
                post_url,
                "post",
                request_data.params,
                request_data.headers,
                post_json,
            )
            # conflicting resource may already exist
            assert (
                response.ok or response.status_code == conflict_status_code
            ), f"get_json_data_with_conflict received {response.status_code}: {response.json()}"
            return json_data
        raise ValueError(
            f"No UniquePropertyValueConstraint in the get_relations list on dto {dto}."
        )

    @keyword
    def authorized_request(  # pylint: disable=too-many-arguments
        self,
        url: str,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Response:
        """
        Perform a request using the security token or authentication set in the library.

        > Note: provided username / password or auth objects take precedence over token
            based security
        """
        headers = headers if headers else {}
        if self.extra_headers:
            headers.update(self.extra_headers)
        # if both an auth object and a token are available, auth takes precedence
        if self.security_token and not self.auth:
            security_header = {"Authorization": self.security_token}
            headers.update(security_header)
        response = self.session.request(
            url=url,
            method=method,
            params=params,
            headers=headers,
            json=json_data,
            auth=self.auth,
            verify=False,
        )
        logger.debug(f"Response text: {response.text}")
        return response
