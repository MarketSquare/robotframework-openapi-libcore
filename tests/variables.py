from OpenApiLibCore import IdReference, DefaultDto, PathPropertiesConstraint


def get_variables():
    id_reference = IdReference(
        property_name="wagegroup_id",
        post_path="/employees",
        error_code=406,
    )
    path_constraint = PathPropertiesConstraint(path="/root"),
    return {
        "ID_REFERENCE": id_reference,
        "PATH_CONSTRAINT": path_constraint,
        "DEFAULT_DTO": DefaultDto(),
    }
