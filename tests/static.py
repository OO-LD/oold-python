import importlib
from typing import Callable, List

import datamodel_code_generator

import oold.model.model as model
from oold.generator import Generator


def _run(
    schemas: List, main_schema: str, test: Callable, pydantic_versions=["v1", "v2"]
):
    for pydantic_version in pydantic_versions:
        if pydantic_version == "v1":
            # from oold.model.v1 import (
            #     ResolveParam,
            #     Resolver,
            #     ResolveResult,
            #     SetResolverParam,
            #     set_resolver,
            # )

            output_model_type = datamodel_code_generator.DataModelType.PydanticBaseModel
        else:
            # from oold.model import (
            #     ResolveParam,
            #     Resolver,
            #     ResolveResult,
            #     SetResolverParam,
            #     set_resolver,
            # )

            output_model_type = (
                datamodel_code_generator.DataModelType.PydanticV2BaseModel
            )

        g = Generator()
        g.generate(
            schemas, main_schema=main_schema, output_model_type=output_model_type
        )
        importlib.reload(model)

        test(pydantic_version)
