"""Custom DRF Schemas."""
from rest_framework.schemas.openapi import AutoSchema


class SysconfigSchema(AutoSchema):
    """Schema for the sysconfig viewset."""

    def get_operation(self, path, method):
        """
        Hard code schema for the sysconfig get operation.

        TODO: Reassess the need for this when drf schema generation is improved.
        """
        operation = {
            "operationId": self._get_operation_id(path, method).capitalize(),
            "responses": {
                "200": {
                    "content": {
                        "application/json": {"schema": {"items": {}, "type": "object"}}
                    },
                    "description": "Retrieve current system configuration.",
                }
            },
        }
        return operation


class ConcurrentSchema(AutoSchema):
    """Schema for the concurrent usage viewset."""

    def get_operation(self, path, method):
        """
        Hard code schema for the concurrent usage get operation.

        TODO: Reassess the need for this when drf schema generation is improved.
        """
        operation = {
            "operationId": "listDailyConcurrentUsages",
            "parameters": [
                {
                    "name": "limit",
                    "required": False,
                    "in": "query",
                    "description": "Number of results to return per page.",
                    "schema": {"type": "integer"},
                },
                {
                    "name": "offset",
                    "required": False,
                    "in": "query",
                    "description": "The initial index from "
                    "which to return the results.",
                    "schema": {"type": "integer"},
                },
            ],
            "responses": {
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "count": {"type": "integer", "example": 123},
                                    "next": {"type": "string", "nullable": True},
                                    "previous": {"type": "string", "nullable": True},
                                    "results": {
                                        "type": "array",
                                        "items": {
                                            "properties": {
                                                "date": {
                                                    "type": "string",
                                                    "format": "date",
                                                },
                                                "maximum_counts": {
                                                    "type": "array",
                                                    "readOnly": True,
                                                },
                                            },
                                            "required": ["date"],
                                        },
                                    },
                                },
                            }
                        }
                    },
                    "description": "Generate report of concurrent "
                    "usage within a time frame.",
                }
            },
        }

        return operation
