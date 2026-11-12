# Python MCP Server for SAP OData — Specialist Profiles

This folder contains role profiles for focused development work on a Python Model Context Protocol (MCP) server that exposes SAP OData services.

## Profiles

- [`Profile_ Python MCP Engineer.md`](<Profile_ Python MCP Engineer.md>) — MCP server implementation and Python code quality.
- [`Profile_ SAP OData Specialist.md`](<Profile_ SAP OData Specialist.md>) — SAP service metadata, OData semantics, and backend behavior.
- [`Profile_ Security Engineer — SAP OData MCP.md`](<Profile_ Security Engineer — SAP OData MCP.md>) — authentication, authorization, secret handling, and risk controls.
- [`Profile_ Test & Quality Engineer.md`](<Profile_ Test & Quality Engineer.md>) — automated tests, fixtures, compatibility, and release readiness.

## Suggested use

Use one profile as the primary role for a focused task, or combine two implementation specialists for a larger feature. The roles are complementary: the SAP specialist defines correct service semantics, the MCP engineer implements the protocol layer, the security engineer reviews access and side effects, and the test engineer verifies behavior.

These are reusable role instructions, not assumptions about a particular SAP product version, identity provider, MCP SDK, transport, or OData version. Confirm those details from the project and target environment before making implementation decisions.
