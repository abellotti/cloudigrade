"""Collection of tests targeting custom schema generation."""
from django.test import TestCase

from api.schemas import ConcurrentSchema, SysconfigSchema
from api.views import SysconfigViewSet


class SchemaTestCase(TestCase):
    """Test custom openapi.json Schema generation."""

    def test_sysconfigschema(self):
        """Test that the sysconfig schema generation returns expected results."""
        schema = SysconfigSchema()
        path = "/api/cloudigrade/v2/sysconfig/"
        method = "GET"
        schema.view = SysconfigViewSet.as_view({"get": "list"})
        spec = schema.get_operation(path, method)

        expected_response = {
            "200": {
                "content": {
                    "application/json": {"schema": {"items": {}, "type": "object"}}
                },
                "description": "Retrieve current system configuration.",
            }
        }

        self.assertIsNotNone(spec["operationId"])
        self.assertEqual(spec["responses"], expected_response)

    def test_concurrentschema(self):
        """Test that the concurrent schema generation returns expected results."""
        schema = ConcurrentSchema()
        path = "/api/cloudigrade/v2/concurrent/"
        method = "GET"
        schema.view = SysconfigViewSet.as_view({"get": "list"})
        spec = schema.get_operation(path, method)

        expected_response = {
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

        self.assertIsNotNone(spec["operationId"])
        self.assertIsNotNone(spec["parameters"])
        self.assertEqual(spec, expected_response)
