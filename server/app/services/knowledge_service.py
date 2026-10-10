"""Curated general programming knowledge base service and seeder for DevMemory."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from pymongo.database import Database

from app.schemas.knowledge import KnowledgeBaseMatch, KnowledgeBaseSeedResponse
from app.services.embedding_service import (
    build_embedding_text,
    get_active_embedding_provider,
    resolve_target_dimension,
    validate_and_normalize_vector,
)

logger = logging.getLogger(__name__)

# 25 Curated General Programming Knowledge Base Entries
CURATED_KNOWLEDGE_ENTRIES: List[Dict[str, Any]] = [
    # --- Python ---
    {
        "kb_id": "kb_py_file_not_found",
        "title": "Python File Not Found Error",
        "error_pattern": "FileNotFoundError: [Errno 2] No such file or directory: '<path>'",
        "language": "python",
        "category": "runtime",
        "explanation": "Python attempted to open or access a file at a path that does not exist relative to the current working directory.",
        "possible_causes": [
            "Relative path resolution difference from current working directory",
            "File was not created or copied prior to execution",
            "Typo in filename or missing directory separator",
        ],
        "diagnostic_checks": [
            "Print Path.cwd() or os.getcwd() to inspect active working directory",
            "Verify file presence using Path(target_path).exists()",
            "Check for absolute vs relative path mismatches",
        ],
        "suggested_resolutions": [
            "Resolve paths relative to project root or __file__ parent",
            "Verify configuration file template exists before script starts",
            "Use Path(__file__).resolve().parent for sibling asset lookups",
        ],
        "tags": ["python", "file", "filesystem", "path", "filenotfounderror"],
    },
    {
        "kb_id": "kb_py_mod_not_found",
        "title": "Python Module Not Found",
        "error_pattern": "ModuleNotFoundError: No module named '<module_name>'",
        "language": "python",
        "category": "runtime",
        "explanation": "Python interpreter cannot locate the imported package in sys.path or the active virtual environment.",
        "possible_causes": [
            "Dependency not installed in the currently active Python interpreter",
            "Command executed against global Python instead of project virtual environment",
            "Local package root missing from sys.path or PYTHONPATH",
        ],
        "diagnostic_checks": [
            "Verify active interpreter with 'Get-Command python' or 'which python'",
            "Inspect installed dependencies with 'pip list'",
            "Check sys.path from interactive Python shell",
        ],
        "suggested_resolutions": [
            "Activate the project virtual environment before running the command",
            "Install missing package via 'pip install <package>' or poetry/pipenv",
            "Ensure PYTHONPATH includes the source directory when running package modules",
        ],
        "tags": ["python", "import", "dependencies", "modulenotfounderror"],
    },
    {
        "kb_id": "kb_py_import_error",
        "title": "Python Import Error / Circular Import",
        "error_pattern": "ImportError: cannot import name '<name>' from partially initialized module '<module>'",
        "language": "python",
        "category": "runtime",
        "explanation": "A circular dependency between two Python modules prevented the requested symbol from resolving during module initialization.",
        "possible_causes": [
            "Circular import between module A and module B importing each other at top-level",
            "Local file shadowing standard library or third-party module name",
            "Symbol name mismatch or outdated cached .pyc bytecode",
        ],
        "diagnostic_checks": [
            "Trace the import dependency chain between the two reported modules",
            "Check for local filenames that collide with installed library names",
            "Clear __pycache__ directories and retry execution",
        ],
        "suggested_resolutions": [
            "Refactor shared functions/classes into a common third utility module",
            "Move one of the imports inside the specific function requiring it",
            "Rename local files that shadow standard library module names",
        ],
        "tags": ["python", "import", "circular", "importerror"],
    },
    {
        "kb_id": "kb_py_type_error",
        "title": "Python Type Mismatch",
        "error_pattern": "TypeError: unsupported operand type(s) for +: '<type1>' and '<type2>'",
        "language": "python",
        "category": "runtime",
        "explanation": "An operation was performed on incompatible data types, such as attempting to add or concatenate a string with an integer.",
        "possible_causes": [
            "Unparsed string received from input, environment variable, or HTTP payload",
            "Variable unexpectedly None or holding a different type than assumed",
            "Missing explicit type cast before arithmetic or string formatting",
        ],
        "diagnostic_checks": [
            "Print type(var) for all operands participating in the expression",
            "Inspect upstream variable assignments and function return signatures",
        ],
        "suggested_resolutions": [
            "Explicitly cast strings to numeric types with int() or float()",
            "Use f-strings for string interpolation instead of direct concatenation",
            "Add isinstance() guards or Pydantic validation at data boundaries",
        ],
        "tags": ["python", "types", "typeerror", "casting"],
    },
    {
        "kb_id": "kb_py_zero_division",
        "title": "Python Division by Zero",
        "error_pattern": "ZeroDivisionError: division by zero",
        "language": "python",
        "category": "runtime",
        "explanation": "An arithmetic division or modulo operation received a denominator with numeric value 0.",
        "possible_causes": [
            "Count or total variable was zero due to empty dataset or collection",
            "Unchecked default value 0 passed into calculation function",
            "Elapsed time or duration evaluated to zero in rapid executions",
        ],
        "diagnostic_checks": [
            "Check divisor value and upstream calculation leading to denominator",
            "Verify whether input collection contains zero elements",
        ],
        "suggested_resolutions": [
            "Add a guard check 'if denominator == 0' returning 0 or default baseline",
            "Use max(1, count) when computing averages to prevent zero denominators",
            "Validate input parameters before performing rate calculations",
        ],
        "tags": ["python", "math", "zerodivisionerror"],
    },
    {
        "kb_id": "kb_py_key_error",
        "title": "Python Dictionary Key Error",
        "error_pattern": "KeyError: '<key_name>'",
        "language": "python",
        "category": "runtime",
        "explanation": "Direct subscript access attempted on a dictionary with a key that does not exist in the mapping.",
        "possible_causes": [
            "Key omitted from incoming JSON request payload or dictionary",
            "Typo in key name or case sensitivity difference",
            "Environment variable not defined when using os.environ[key]",
        ],
        "diagnostic_checks": [
            "Print dict.keys() to inspect actual keys present in the dictionary",
            "Check whether key is optional or conditionally populated",
        ],
        "suggested_resolutions": [
            "Use dict.get(key, default) for safe retrieval with fallback value",
            "Use 'if key in my_dict:' check before direct access",
            "Use os.getenv(key, default) instead of direct os.environ subscripting",
        ],
        "tags": ["python", "dictionary", "keyerror"],
    },

    # --- JavaScript / Node.js ---
    {
        "kb_id": "kb_js_reference_error",
        "title": "JavaScript Undefined Variable Reference",
        "error_pattern": "ReferenceError: <variable> is not defined",
        "language": "javascript",
        "category": "runtime",
        "explanation": "JavaScript engine encountered an identifier that has not been declared in the current or outer scopes.",
        "possible_causes": [
            "Typo in variable, function, or parameter name",
            "Variable declared with let/const inside an inner block and accessed outside",
            "Missing import or require statement for external module identifier",
        ],
        "diagnostic_checks": [
            "Check scope and declaration of the identifier",
            "Verify imports at top of file",
        ],
        "suggested_resolutions": [
            "Declare variable with const, let, or pass it as function argument",
            "Import the required module identifier before referencing",
            "Correct variable naming typos",
        ],
        "tags": ["javascript", "nodejs", "referenceerror", "scope"],
    },
    {
        "kb_id": "kb_js_type_error_null",
        "title": "JavaScript Property Access on Null or Undefined",
        "error_pattern": "TypeError: Cannot read properties of undefined (reading '<property>')",
        "language": "javascript",
        "category": "runtime",
        "explanation": "Attempted to access a property or call a method on an object whose value is undefined or null.",
        "possible_causes": [
            "Asynchronous API call returned empty or error response before property lookup",
            "Object initialization failed or optional nested property omitted",
            "Array find() or lookup returned undefined when element was not found",
        ],
        "diagnostic_checks": [
            "Log the parent object before accessing nested properties",
            "Check whether asynchronous promise resolved successfully before accessing data",
        ],
        "suggested_resolutions": [
            "Use optional chaining: object?.property?.subproperty",
            "Provide default value with nullish coalescing: (object?.property ?? defaultVal)",
            "Guard with 'if (object) { ... }' prior to property access",
        ],
        "tags": ["javascript", "nodejs", "typeerror", "null", "undefined"],
    },
    {
        "kb_id": "kb_js_module_not_found",
        "title": "Node.js Cannot Find Module",
        "error_pattern": "Error: Cannot find module '<module_name>'",
        "language": "javascript",
        "category": "runtime",
        "explanation": "Node.js runtime module resolver failed to locate the specified package in node_modules or relative path.",
        "possible_causes": [
            "npm package has not been installed in local node_modules",
            "Relative file path in require() or import statement is incorrect",
            "Missing package.json entry or failed npm/yarn install",
        ],
        "diagnostic_checks": [
            "Check if target package exists in node_modules directory",
            "Verify package.json dependencies list",
            "Verify relative path starts with './' or '../'",
        ],
        "suggested_resolutions": [
            "Run 'npm install' or 'npm install <package>' to install missing package",
            "Ensure relative path has correct relative prefix (./file.js instead of file.js)",
            "Verify file extension compatibility (.js, .mjs, .cjs)",
        ],
        "tags": ["javascript", "nodejs", "modules", "npm"],
    },

    # --- HTTP / API ---
    {
        "kb_id": "kb_http_400_bad_request",
        "title": "HTTP 400 Bad Request",
        "error_pattern": "HTTP 400 Bad Request",
        "language": "http",
        "category": "api",
        "explanation": "The server cannot or will not process the request due to an apparent client error (e.g. malformed syntax, invalid payload schema).",
        "possible_causes": [
            "JSON payload syntax error or invalid data types in request body",
            "Missing required query parameter or header",
            "Request validation schema failed (e.g. Pydantic / Joi validation error)",
        ],
        "diagnostic_checks": [
            "Inspect server response body for validation error details",
            "Verify request body is valid JSON with Content-Type: application/json header",
        ],
        "suggested_resolutions": [
            "Align request payload structure with server API schema specifications",
            "Verify mandatory request headers and query parameters are supplied",
            "Validate payload types before sending request",
        ],
        "tags": ["http", "api", "400", "badrequest", "validation"],
    },
    {
        "kb_id": "kb_http_401_unauthorized",
        "title": "HTTP 401 Unauthorized",
        "error_pattern": "HTTP 401 Unauthorized",
        "language": "http",
        "category": "api",
        "explanation": "The requested resource requires user authentication credentials that are either missing or invalid.",
        "possible_causes": [
            "Authorization header missing or empty",
            "API key or bearer token expired or revoked",
            "Token format incorrect (e.g. missing 'Bearer ' prefix)",
        ],
        "diagnostic_checks": [
            "Check if Authorization header is set on the request",
            "Verify token expiration timestamp",
        ],
        "suggested_resolutions": [
            "Provide valid API key or token in Authorization header",
            "Refresh or re-issue expired session credentials",
            "Verify authorization scheme (Bearer vs Basic vs ApiKey)",
        ],
        "tags": ["http", "api", "401", "authentication", "auth"],
    },
    {
        "kb_id": "kb_http_403_forbidden",
        "title": "HTTP 403 Forbidden",
        "error_pattern": "HTTP 403 Forbidden",
        "language": "http",
        "category": "api",
        "explanation": "The client identity is known, but the authenticated user lacks authorization permissions to access the requested resource.",
        "possible_causes": [
            "User role or scope does not include required access permissions",
            "Access to another tenant's private resource attempted",
            "IP address or origin disallowed by server CORS/allowlist policy",
        ],
        "diagnostic_checks": [
            "Verify assigned permissions and roles for authenticated identity",
            "Check resource ownership and tenant isolation boundaries",
        ],
        "suggested_resolutions": [
            "Grant necessary role or scope permission on the resource",
            "Verify request operates within caller's authorized tenant boundary",
            "Check server CORS origin configuration",
        ],
        "tags": ["http", "api", "403", "authorization", "rbac"],
    },
    {
        "kb_id": "kb_http_404_not_found",
        "title": "HTTP 404 Not Found",
        "error_pattern": "HTTP 404 Not Found",
        "language": "http",
        "category": "api",
        "explanation": "The server cannot locate the requested endpoint URL or target resource identifier.",
        "possible_causes": [
            "Typo or missing prefix in URL path (e.g. missing /api/v1 prefix)",
            "Referenced entity ID does not exist in the database",
            "HTTP method mismatch on route (e.g. GET instead of POST)",
        ],
        "diagnostic_checks": [
            "Verify endpoint route path against OpenAPI / Swagger documentation",
            "Check if target ID exists in underlying database",
        ],
        "suggested_resolutions": [
            "Verify full API URL path and base URL configuration",
            "Confirm resource existence before issuing dependent requests",
            "Verify HTTP verb (GET, POST, PUT, DELETE) matches route definition",
        ],
        "tags": ["http", "api", "404", "notfound", "routing"],
    },
    {
        "kb_id": "kb_http_500_internal_error",
        "title": "HTTP 500 Internal Server Error",
        "error_pattern": "HTTP 500 Internal Server Error",
        "language": "http",
        "category": "api",
        "explanation": "The server encountered an unhandled exception or fatal condition that prevented fulfilling the request.",
        "possible_causes": [
            "Unhandled runtime exception in backend controller or service layer",
            "Database query failure or connection loss",
            "Null pointer / undefined variable crash in server handler",
        ],
        "diagnostic_checks": [
            "Inspect backend server application logs for the traceback",
            "Check health of database and dependent microservices",
        ],
        "suggested_resolutions": [
            "Wrap controller logic in appropriate exception handlers",
            "Inspect server traceback to locate the failing line in service layer",
            "Verify backend database connectivity and migrations",
        ],
        "tags": ["http", "api", "500", "server", "exception"],
    },

    # --- MongoDB ---
    {
        "kb_id": "kb_mongo_connection_timeout",
        "title": "MongoDB Server Selection Timeout",
        "error_pattern": "ServerSelectionTimeoutError: No replica set members match selector",
        "language": "mongodb",
        "category": "database",
        "explanation": "MongoDB client failed to establish connection with any cluster nodes within the configured server selection timeout.",
        "possible_causes": [
            "Network block or IP address not whitelisted in MongoDB Atlas Network Access",
            "Incorrect hostname or cluster URI in connection string",
            "Local network offline, proxy interception, or firewall block on port 27017",
        ],
        "diagnostic_checks": [
            "Verify current outbound IP address is added to Atlas IP Access List",
            "Test cluster connectivity using mongosh or network ping",
            "Check TLS/SSL settings and certificates",
        ],
        "suggested_resolutions": [
            "Add current IP address (or 0.0.0.0/0 for development) in Atlas Network Access",
            "Verify MONGODB_URI connection string hostname is accurate",
            "Increase serverSelectionTimeoutMS if network latency is high",
        ],
        "tags": ["mongodb", "database", "connection", "timeout", "atlas"],
    },
    {
        "kb_id": "kb_mongo_auth_failure",
        "title": "MongoDB Authentication Failure",
        "error_pattern": "OperationFailure: Authentication failed.",
        "language": "mongodb",
        "category": "database",
        "explanation": "MongoDB server rejected the provided username or password for the specified authentication database.",
        "possible_causes": [
            "Incorrect database username or password in connection string",
            "Special characters in password not percent-encoded in connection URI",
            "User not granted readWrite permissions on target database",
            "authSource parameter missing or incorrect (default is 'admin')",
        ],
        "diagnostic_checks": [
            "Verify database user credentials in MongoDB Atlas Database Access tab",
            "Check authSource query parameter in connection URI",
        ],
        "suggested_resolutions": [
            "Percent-encode special characters in password (e.g. '@' -> '%40')",
            "Ensure database user has readWrite role on the target database",
            "Add '?authSource=admin' to connection URI if authenticating against admin",
        ],
        "tags": ["mongodb", "database", "auth", "authentication"],
    },

    # --- Dependencies ---
    {
        "kb_id": "kb_dep_version_conflict",
        "title": "Dependency Version Incompatibility",
        "error_pattern": "ResolutionImpossible: Dependency version conflict detected",
        "language": "general",
        "category": "dependencies",
        "explanation": "Package package manager cannot find a set of package versions satisfying all declared version constraints simultaneously.",
        "possible_causes": [
            "Two packages require mutually incompatible versions of a shared dependency",
            "Pinned version conflicts with newly installed library requirements",
            "Python/Node engine runtime version mismatch with package requirements",
        ],
        "diagnostic_checks": [
            "Run 'pip check' or 'npm ls' to view conflicting dependency tree",
            "Inspect requirements.txt or package.json version constraints",
        ],
        "suggested_resolutions": [
            "Relax overly strict version pins (e.g. 'pkg==1.0' -> 'pkg>=1.0,<2.0')",
            "Upgrade downstream packages to versions supporting modern dependencies",
            "Use virtual environments with isolated dependency trees",
        ],
        "tags": ["dependencies", "pip", "npm", "packages", "conflict"],
    },

    # --- Git ---
    {
        "kb_id": "kb_git_merge_conflict",
        "title": "Git Merge Conflict",
        "error_pattern": "CONFLICT (content): Merge conflict in <file>",
        "language": "git",
        "category": "vcs",
        "explanation": "Git cannot automatically reconcile divergent edits made to the same lines of a file across merged branches.",
        "possible_causes": [
            "Same file edited and committed concurrently on both target and source branches",
            "Upstream branch updated before local branch rebase or merge",
        ],
        "diagnostic_checks": [
            "Run 'git status' to list unmerged paths",
            "Search for conflict markers '<<<<<<<', '=======', '>>>>>>>' in affected files",
        ],
        "suggested_resolutions": [
            "Open conflicted files, resolve overlapping lines, and remove conflict markers",
            "Stage resolved files with 'git add <file>'",
            "Complete merge with 'git commit' or 'git rebase --continue'",
        ],
        "tags": ["git", "vcs", "merge", "conflict"],
    },
    {
        "kb_id": "kb_git_push_rejected",
        "title": "Git Non-Fast-Forward Push Rejected",
        "error_pattern": "error: failed to push some refs ... Updates were rejected because the remote contains work that you do not have locally",
        "language": "git",
        "category": "vcs",
        "explanation": "Remote branch contains commits that are not present in your local working branch, preventing a clean fast-forward update.",
        "possible_causes": [
            "Teammate pushed commits to remote branch since your last pull",
            "Commit history diverged after remote rebasing",
        ],
        "diagnostic_checks": [
            "Run 'git fetch origin' to view remote branch state",
            "Run 'git log ..origin/<branch>' to inspect incoming commits",
        ],
        "suggested_resolutions": [
            "Pull incoming changes with 'git pull --rebase origin <branch>'",
            "Resolve any local rebase conflicts and test before pushing",
            "Avoid force-pushing to shared branches",
        ],
        "tags": ["git", "vcs", "push", "remote"],
    },

    # --- Configuration ---
    {
        "kb_id": "kb_cfg_missing_env_var",
        "title": "Missing Required Environment Variable",
        "error_pattern": "KeyError: '<ENV_VAR>' or ValidationError: Field '<ENV_VAR>' required",
        "language": "configuration",
        "category": "configuration",
        "explanation": "Application startup halted because an essential environment variable is missing from the environment.",
        "possible_causes": [
            ".env file was not loaded or does not exist in the working directory",
            "Variable defined in example file (e.g. .env.example) but not in actual .env",
            "Subprocess or container launched without inheriting parent environment",
        ],
        "diagnostic_checks": [
            "Verify .env file exists in the active project directory",
            "Inspect process environment using os.environ or Get-ChildItem Env:",
        ],
        "suggested_resolutions": [
            "Copy .env.example to .env and configure local parameters",
            "Use load_dotenv() or Pydantic BaseSettings to load environment file automatically",
            "Provide safe fallback defaults for non-critical configuration settings",
        ],
        "tags": ["configuration", "environment", "dotenv", "env"],
    },
    {
        "kb_id": "kb_cfg_port_conflict",
        "title": "Address Already in Use / Port Conflict",
        "error_pattern": "EADDRINUSE: address already in use <host>:<port> or [Errno 98] Address already in use",
        "language": "networking",
        "category": "networking",
        "explanation": "The server failed to bind to the requested network port because another process is already listening on that port.",
        "possible_causes": [
            "Previous server process did not shut down completely and remains running in background",
            "Another application or service bound to the same port (e.g. 8000, 3000, 5000)",
        ],
        "diagnostic_checks": [
            "On Windows run 'netstat -ano | findstr :<port>' to identify process PID",
            "On Linux/macOS run 'lsof -i :<port>' or 'netstat -tulpn'",
        ],
        "suggested_resolutions": [
            "Terminate the lingering process using Task Manager or Stop-Process / kill",
            "Configure application to use an alternative port via environment variable or CLI argument",
            "Ensure servers handle shutdown signals cleanly to release sockets",
        ],
        "tags": ["networking", "ports", "eaddrinuse", "socket"],
    },

    # --- Testing ---
    {
        "kb_id": "kb_test_assertion_error",
        "title": "Test Assertion Failure",
        "error_pattern": "AssertionError: assert <left> == <right>",
        "language": "testing",
        "category": "testing",
        "explanation": "A test assertion evaluated to False, indicating actual program output deviated from expected behavior.",
        "possible_causes": [
            "Regression introduced into calculation, serializer, or business logic",
            "Test expected data was not updated following an intentional design change",
            "Non-deterministic test data (e.g. random numbers, unpinned dates/times)",
        ],
        "diagnostic_checks": [
            "Inspect the failure diff showing differences between actual and expected",
            "Run single test in isolation with pytest -k <test_name> -vv",
        ],
        "suggested_resolutions": [
            "Fix underlying application bug identified by the assertion discrepancy",
            "Update test fixture or assertion if API contract intentionally changed",
            "Mock time, random generation, and external dependencies for test determinism",
        ],
        "tags": ["testing", "pytest", "assertion", "unit-test"],
    },
    {
        "kb_id": "kb_test_timeout",
        "title": "Test Execution Timeout",
        "error_pattern": "TimeoutError: Test execution exceeded timeout limit",
        "language": "testing",
        "category": "testing",
        "explanation": "A test suite or individual test failed to finish within the maximum allotted time limit.",
        "possible_causes": [
            "Asynchronous promise or callback never resolved or rejected",
            "Live network or external service call attempted without mocking",
            "Infinite loop or blocking I/O operation in test path",
        ],
        "diagnostic_checks": [
            "Check whether external services or databases are mocked in tests",
            "Inspect async await statements to verify promises complete",
        ],
        "suggested_resolutions": [
            "Mock all external network requests using responses, httpx-mock, or unittest.mock",
            "Ensure async routines properly resolve or have bounded timeouts",
            "Increase timeout threshold only for legitimate heavy integration benchmarks",
        ],
        "tags": ["testing", "timeout", "async"],
    },

    # --- Networking ---
    {
        "kb_id": "kb_net_conn_refused",
        "title": "Network Connection Refused",
        "error_pattern": "ConnectionRefusedError: [Errno 111] Connection refused or ECONNREFUSED <host>:<port>",
        "language": "networking",
        "category": "networking",
        "explanation": "The target host actively rejected the connection because no service is running and listening on the destination port.",
        "possible_causes": [
            "Destination service (e.g. Redis, Postgres, API backend) is not started",
            "Client attempted connection to wrong port or localhost instead of container network",
            "Service bound strictly to 127.0.0.1 and cannot be reached from external network",
        ],
        "diagnostic_checks": [
            "Verify destination service is active using systemctl status or docker ps",
            "Check destination service listening host and port configuration",
        ],
        "suggested_resolutions": [
            "Start the required background service before launching the client application",
            "Verify host and port parameters in client configuration match server settings",
            "Bind server to 0.0.0.0 if connecting across container or network boundaries",
        ],
        "tags": ["networking", "connection", "econnrefused", "service"],
    },
    {
        "kb_id": "kb_net_request_timeout",
        "title": "Network Request Timeout",
        "error_pattern": "Timeout: Request timed out while waiting for response",
        "language": "networking",
        "category": "networking",
        "explanation": "Client established connection but failed to receive a response from remote server within timeout threshold.",
        "possible_causes": [
            "Remote server overloaded, deadlocked, or performing long-running unindexed query",
            "Intermediate gateway or proxy dropped the connection",
            "Client timeout parameter configured too aggressively for the operation",
        ],
        "diagnostic_checks": [
            "Measure network latency and upstream server response times",
            "Check upstream server health and CPU/memory utilization",
        ],
        "suggested_resolutions": [
            "Implement exponential backoff retry policy with jitter for transient latency",
            "Tune upstream query performance with proper database indexing",
            "Adjust client timeout to a reasonable threshold for the workload",
        ],
        "tags": ["networking", "timeout", "http", "latency"],
    },
]


def seed_knowledge_base(
    db: Database,
    force_reembed: bool = False,
) -> KnowledgeBaseSeedResponse:
    """Idempotently seed the curated programming knowledge base into MongoDB.

    Guarantees:
    - Never inserts duplicates (keyed on unique kb_id).
    - Preserves existing records unless content changes.
    - Computes vector embeddings using configured Voyage AI provider (or deterministic fallback).
    - Accurately reports whether live Voyage AI embedding or deterministic fallback was used.
    - Never marks curated records as verified fix resolutions.
    - Never exposes raw credentials or API keys.
    """
    total = len(CURATED_KNOWLEDGE_ENTRIES)
    inserted = 0
    updated = 0
    unchanged = 0

    target_dim = resolve_target_dimension()
    active_prov = get_active_embedding_provider(dimension=target_dim)
    prov_name = getattr(active_prov, "provider_name", "voyage")
    is_fallback = getattr(active_prov, "is_fallback", False)
    emb_model = getattr(active_prov, "model", "voyage-code-4")
    emb_status = "deterministic_fallback" if is_fallback else "live_success"

    now = datetime.now(timezone.utc)

    for entry in CURATED_KNOWLEDGE_ENTRIES:
        kb_id = entry["kb_id"]
        existing = db.knowledge_base.find_one({"kb_id": kb_id})

        # Canonical text for embedding
        canonical_text = build_embedding_text(
            error_message=f"{entry['title']}: {entry['error_pattern']}",
            stack_trace=f"{entry['explanation']} {' '.join(entry['suggested_resolutions'])}",
            command=entry.get("language"),
        )

        needs_embedding = force_reembed or existing is None or "embedding" not in existing

        embedding_vector = None
        if needs_embedding:
            try:
                if hasattr(active_prov, "get_embedding_with_status"):
                    res = active_prov.get_embedding_with_status(canonical_text, input_type="document")
                    raw_vec = res.vector
                else:
                    raw_vec = active_prov.get_embedding(canonical_text)
                embedding_vector = validate_and_normalize_vector(raw_vec, target_dim, allow_zero=True)
            except Exception as exc:
                logger.warning("Embedding generation for kb_id '%s' failed (%s); using zero vector fallback.", kb_id, exc)
                embedding_vector = [0.0] * target_dim

        doc_update: Dict[str, Any] = {
            "title": entry["title"],
            "error_pattern": entry["error_pattern"],
            "language": entry["language"],
            "category": entry["category"],
            "explanation": entry["explanation"],
            "possible_causes": entry["possible_causes"],
            "diagnostic_checks": entry["diagnostic_checks"],
            "suggested_resolutions": entry["suggested_resolutions"],
            "tags": entry["tags"],
            "source_type": "knowledge_base",
            "updated_at": now,
        }

        if embedding_vector is not None:
            doc_update["embedding"] = embedding_vector
            doc_update["embedding_model"] = emb_model
            doc_update["embedding_dimension"] = target_dim
            doc_update["embedding_status"] = emb_status

        if existing is None:
            doc_update["kb_id"] = kb_id
            doc_update["created_at"] = now
            db.knowledge_base.insert_one(doc_update)
            inserted += 1
        else:
            # Check if updated fields differ
            is_diff = False
            for k in ["title", "error_pattern", "explanation", "language", "category"]:
                if existing.get(k) != entry[k]:
                    is_diff = True
                    break
            if is_diff or needs_embedding:
                db.knowledge_base.update_one({"kb_id": kb_id}, {"$set": doc_update})
                updated += 1
            else:
                unchanged += 1

    msg = f"Knowledge base seeded successfully: {inserted} inserted, {updated} updated, {unchanged} unchanged across {total} curated entries."
    logger.info(msg)

    return KnowledgeBaseSeedResponse(
        total_curated=total,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        embedding_provider=prov_name,
        embedding_status=emb_status,
        embedding_dimension=target_dim,
        message=msg,
    )


def list_knowledge_base_items(
    db: Database,
    language: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Retrieve items from knowledge base collection."""
    filter_q: Dict[str, Any] = {}
    if language:
        filter_q["language"] = language.lower()
    if category:
        filter_q["category"] = category.lower()

    cursor = db.knowledge_base.find(filter_q, {"_id": 0}).limit(limit)
    return list(cursor)


def search_knowledge_base(
    db: Database,
    query_text: str,
    limit: int = 5,
    min_score: float = 0.40,
) -> List[KnowledgeBaseMatch]:
    """Search knowledge base using token matching and vector cosine similarity.

    Guarantees:
    - Never returns project incident data (strictly scopes to knowledge_base collection).
    - Distinguishable provenance: returns source='knowledge_base'.
    - Returns empty list if no items meet min_score.
    """
    if not query_text or not query_text.strip():
        return []

    clean_query = query_text.lower().strip()
    query_tokens = set(clean_query.split())

    # Pre-generate query vector if embedding provider is available
    target_dim = resolve_target_dimension()
    active_prov = get_active_embedding_provider(dimension=target_dim)
    try:
        if hasattr(active_prov, "get_embedding_with_status"):
            q_res = active_prov.get_embedding_with_status(clean_query, input_type="query")
            query_vec = q_res.vector
        else:
            raw_vec = active_prov.get_embedding(clean_query)
            query_vec = validate_and_normalize_vector(raw_vec, target_dim, allow_zero=True)
    except Exception:
        query_vec = None

    cursor = db.knowledge_base.find({}, {"_id": 0})
    candidates: List[tuple[float, Dict[str, Any]]] = []

    for item in cursor:
        score = 0.0

        # 1. Lexical token & pattern score
        title = item.get("title", "").lower()
        err_pat = item.get("error_pattern", "").lower()
        tags = [t.lower() for t in item.get("tags", [])]
        expl = item.get("explanation", "").lower()

        # Exact substring matches
        if clean_query in err_pat or err_pat in clean_query:
            score = max(score, 0.95)
        elif any(t in clean_query for t in tags if len(t) > 3):
            score = max(score, 0.70)

        # Token intersection
        item_tokens = set(title.split() + err_pat.split() + tags)
        shared = query_tokens.intersection(item_tokens)
        if shared:
            token_score = len(shared) / max(len(query_tokens), 1) * 0.85
            score = max(score, token_score)

        # 2. Vector cosine score if embeddings are available
        stored_vec = item.get("embedding")
        if query_vec and stored_vec and len(stored_vec) == len(query_vec):
            dot = sum(a * b for a, b in zip(query_vec, stored_vec))
            vec_score = max(0.0, min(1.0, dot))
            score = max(score, vec_score)

        if score >= min_score:
            candidates.append((score, item))

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:limit]

    return [
        KnowledgeBaseMatch(
            kb_id=item["kb_id"],
            title=item.get("title", ""),
            error_pattern=item.get("error_pattern", ""),
            language=item.get("language", "general"),
            category=item.get("category", "general"),
            explanation=item.get("explanation", ""),
            suggested_resolutions=item.get("suggested_resolutions", []),
            similarity_score=round(score, 4),
            source="knowledge_base",
        )
        for score, item in top
    ]
