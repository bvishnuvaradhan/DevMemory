/**
 * DevMemory - Demonstration & Mock Data Harness
 *
 * NOTE: This file provides realistic demonstration data for development,
 * testing, and offline demonstration. It is explicitly labeled as mock data
 * and must never be misrepresented as live production telemetry.
 */

export const IS_MOCK_DATA = true;
export const MOCK_DATA_DISCLAIMER = "DEMO DATA: Showing demonstration dataset. Real backend not connected.";

export const MOCK_PROJECTS = [
  {
    id: "proj_auth_service",
    name: "auth-service",
    description: "Core OAuth2 & JWT Authentication Microservice",
    language: "Python 3.12",
    framework: "FastAPI",
    repository: "github.com/org/auth-service",
    totalRuns: 64,
    failureCount: 9,
    verifiedFixCount: 7,
    lastRunAt: "2026-10-10T12:15:30Z",
    lastRunStatus: "failure",
    medianDurationMs: 145,
    baselineDurationMs: 130,
  },
  {
    id: "proj_payment_worker",
    name: "payment-worker",
    description: "Idempotent Stripe webhook and payout batch processor",
    language: "TypeScript / Node.js 20",
    framework: "Express / BullMQ",
    repository: "github.com/org/payment-worker",
    totalRuns: 42,
    failureCount: 5,
    verifiedFixCount: 4,
    lastRunAt: "2026-10-10T11:58:12Z",
    lastRunStatus: "success",
    medianDurationMs: 310,
    baselineDurationMs: 315,
  },
  {
    id: "proj_data_pipeline",
    name: "data-pipeline",
    description: "Distributed feature extraction and tensor preprocessing",
    language: "Python 3.11",
    framework: "PyTorch / Polars",
    repository: "github.com/org/data-pipeline",
    totalRuns: 28,
    failureCount: 8,
    verifiedFixCount: 5,
    lastRunAt: "2026-10-10T10:45:00Z",
    lastRunStatus: "failure",
    medianDurationMs: 1420,
    baselineDurationMs: 1100,
  },
  {
    id: "proj_checkout_web",
    name: "checkout-web",
    description: "Customer checkout web client & cart flow",
    language: "TypeScript",
    framework: "React 18 / Vite",
    repository: "github.com/org/checkout-web",
    totalRuns: 35,
    failureCount: 4,
    verifiedFixCount: 4,
    lastRunAt: "2026-10-10T09:30:21Z",
    lastRunStatus: "success",
    medianDurationMs: 88,
    baselineDurationMs: 90,
  },
  {
    id: "proj_notification_service",
    name: "notification-service",
    description: "Real-time multi-channel notification dispatcher & queue consumer",
    language: "Go 1.22",
    framework: "Gin / Redis",
    repository: "github.com/org/notification-service",
    totalRuns: 52,
    failureCount: 2,
    verifiedFixCount: 2,
    lastRunAt: "2026-10-10T12:30:00Z",
    lastRunStatus: "success",
    medianDurationMs: 45,
    baselineDurationMs: 50,
  },
];

export const MOCK_GLOBAL_STATS = {
  totalProjects: 5,
  totalRuns: 221,
  totalFailures: 28,
  failureRate: "12.7%",
  verifiedFixes: 22,
  verifiedFixRate: "78.6%",
  recurringErrorsCount: 3,
  medianExecutionTimeMs: 145,
  activeIncidentsCount: 6,
  isMock: true,
};

export const MOCK_RECENT_RUNS = [
  {
    eventId: "evt_3f8c12a0",
    projectId: "proj_notification_service",
    projectName: "notification-service",
    command: "go test ./cmd/dispatcher/...",
    exitCode: 0,
    status: "success",
    durationMs: 45,
    timestamp: "2026-10-10T12:30:00Z",
    errorSummary: null,
    sourceFile: null,
    lineNumber: null,
  },
  {
    eventId: "evt_9b1a7f40",
    projectId: "proj_auth_service",
    projectName: "auth-service",
    command: "pytest tests/test_token_refresh.py -v",
    exitCode: 1,
    status: "failed",
    durationMs: 428,
    timestamp: "2026-10-10T12:15:30Z",
    errorSummary: "jwt.exceptions.ExpiredSignatureError: Signature has expired",
    sourceFile: "auth/tokens.py",
    lineNumber: 84,
  },
  {
    eventId: "evt_8c2b6e31",
    projectId: "proj_payment_worker",
    projectName: "payment-worker",
    command: "npm test -- tests/webhook.test.ts",
    exitCode: 0,
    status: "success",
    durationMs: 295,
    timestamp: "2026-10-10T11:58:12Z",
    errorSummary: null,
    sourceFile: null,
    lineNumber: null,
  },
  {
    eventId: "evt_7d3c5d22",
    projectId: "proj_data_pipeline",
    projectName: "data-pipeline",
    command: "python -m pipeline.preprocess --batch-size 128",
    exitCode: 137,
    status: "failed",
    durationMs: 2840,
    timestamp: "2026-10-10T10:45:00Z",
    errorSummary: "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.40 GiB",
    sourceFile: "pipeline/loader.py",
    lineNumber: 142,
  },
  {
    eventId: "evt_6e4d4c13",
    projectId: "proj_checkout_web",
    projectName: "checkout-web",
    command: "npm run build",
    exitCode: 0,
    status: "success",
    durationMs: 1420,
    timestamp: "2026-10-10T09:30:21Z",
    errorSummary: null,
    sourceFile: null,
    lineNumber: null,
  },
  {
    eventId: "evt_5f5e3b04",
    projectId: "proj_auth_service",
    projectName: "auth-service",
    command: "alembic upgrade head",
    exitCode: 0,
    status: "success",
    durationMs: 610,
    timestamp: "2026-10-10T09:12:05Z",
    errorSummary: null,
    sourceFile: null,
    lineNumber: null,
  },
  {
    eventId: "evt_4a6f2a95",
    projectId: "proj_data_pipeline",
    projectName: "data-pipeline",
    command: "pytest tests/test_tensor_shapes.py",
    exitCode: 1,
    status: "failed",
    durationMs: 915,
    timestamp: "2026-10-10T08:50:18Z",
    errorSummary: "RuntimeError: The size of tensor a (64) must match the size of tensor b (128)",
    sourceFile: "models/encoder.py",
    lineNumber: 57,
  },
];

export const MOCK_RECURRING_ERRORS = [
  {
    errorType: "ExpiredSignatureError",
    category: "Authentication / Security",
    occurrences: 7,
    affectedProjects: ["auth-service"],
    firstSeen: "2026-10-08T14:20:00Z",
    lastSeen: "2026-10-10T12:15:30Z",
    hasVerifiedFix: true,
    sampleMessage: "jwt.exceptions.ExpiredSignatureError: Signature has expired in token validation",
  },
  {
    errorType: "OutOfMemoryError (CUDA)",
    category: "Resource / Hardware",
    occurrences: 5,
    affectedProjects: ["data-pipeline"],
    firstSeen: "2026-10-09T09:10:00Z",
    lastSeen: "2026-10-10T10:45:00Z",
    hasVerifiedFix: true,
    sampleMessage: "torch.cuda.OutOfMemoryError: Tried to allocate 2.40 GiB (GPU 0; 11.76 GiB total capacity)",
  },
  {
    errorType: "StripeIdempotencyKeyError",
    category: "Third-Party API",
    occurrences: 4,
    affectedProjects: ["payment-worker", "checkout-web"],
    firstSeen: "2026-10-07T18:40:00Z",
    lastSeen: "2026-10-09T16:22:10Z",
    hasVerifiedFix: true,
    sampleMessage: "StripeInvalidRequestError: Keys for idempotent requests can only be used with identical parameters",
  },
];

export const MOCK_VERIFIED_FIXES = [
  {
    id: "fix_01",
    projectName: "auth-service",
    errorType: "ExpiredSignatureError",
    solutionSummary: "Added leeway window (leeway=30s) to jwt.decode() and refresh token clock skew tolerance",
    verificationMethod: "devmemory run -- pytest tests/test_token_refresh.py -k test_clock_skew",
    status: "VERIFIED",
    verifiedAt: "2026-10-09T16:45:00Z",
    recurrenceCountAfterFix: 0,
    author: "AI Recommendation + Developer Verification",
  },
  {
    id: "fix_02",
    projectName: "data-pipeline",
    errorType: "OutOfMemoryError (CUDA)",
    solutionSummary: "Implemented gradient checkpointing and dynamic batch sizing with torch.cuda.empty_cache() on fallback",
    verificationMethod: "devmemory run -- python -m pipeline.preprocess --eval-batch-memory",
    status: "VERIFIED",
    verifiedAt: "2026-10-09T14:10:00Z",
    recurrenceCountAfterFix: 0,
    author: "AI Recommendation + Developer Verification",
  },
  {
    id: "fix_03",
    projectName: "payment-worker",
    errorType: "StripeIdempotencyKeyError",
    solutionSummary: "Scoped idempotency keys with SHA-256 payload digest rather than raw user_id timestamp",
    verificationMethod: "devmemory run -- npm test -- tests/idempotency.test.ts",
    status: "VERIFIED",
    verifiedAt: "2026-10-08T19:30:00Z",
    recurrenceCountAfterFix: 0,
    author: "Cross-Project Memory Hit (from checkout-web) + Verified",
  },
];

export const MOCK_PERFORMANCE_TREND = [
  { runIndex: 1, timestamp: "10:00", durationMs: 140, baselineMs: 130, status: "normal" },
  { runIndex: 2, timestamp: "10:30", durationMs: 135, baselineMs: 130, status: "normal" },
  { runIndex: 3, timestamp: "11:00", durationMs: 150, baselineMs: 130, status: "normal" },
  { runIndex: 4, timestamp: "11:30", durationMs: 142, baselineMs: 130, status: "normal" },
  { runIndex: 5, timestamp: "12:00", durationMs: 290, baselineMs: 130, status: "regression" },
  { runIndex: 6, timestamp: "12:15", durationMs: 428, baselineMs: 130, status: "regression" },
];

export const MOCK_INCIDENTS = [
  {
    incidentId: "inc_auth_01",
    eventId: "evt_9b1a7f40",
    projectId: "proj_auth_service",
    projectName: "auth-service",
    timestamp: "2026-10-10T12:15:30Z",
    command: "pytest tests/test_token_refresh.py -v",
    exitCode: 1,
    errorType: "ExpiredSignatureError",
    errorMessage: "jwt.exceptions.ExpiredSignatureError: Signature has expired in token validation",
    sourceLocation: {
      file: "auth/tokens.py",
      line: 84,
      column: 12,
      snippet: `80: def verify_token(token: str) -> TokenPayload:
81:     try:
82:         payload = jwt.decode(
83:             token,
84:             settings.JWT_SECRET_KEY,  # <-- ExpiredSignatureError raised here
85:             algorithms=[settings.ALGORITHM],
86:         )
87:         return TokenPayload(**payload)
88:     except jwt.PyJWTError as exc:
89:         raise InvalidTokenException(str(exc))`,
    },
    stackTrace: `Traceback (most recent call last):
  File "/app/tests/test_token_refresh.py", line 42, in test_expired_token_refresh
    token_data = verify_token(sample_access_token)
  File "/app/auth/tokens.py", line 84, in verify_token
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
  File "/usr/local/lib/python3.12/site-packages/jwt/api_jwt.py", line 210, in decode
    self._validate_claims(payload, merged_options, ...)
  File "/usr/local/lib/python3.12/site-packages/jwt/api_jwt.py", line 290, in _validate_claims
    raise ExpiredSignatureError("Signature has expired")
jwt.exceptions.ExpiredSignatureError: Signature has expired`,
    aiDiagnosis: {
      observedEvidence: [
        "Token's 'exp' Unix timestamp (1760098520) is 14 seconds earlier than current host clock (1760098534).",
        "jwt.decode() invoked with no 'leeway' tolerance argument.",
        "Test executed in CI environment without NTP clock synchronization daemon active.",
      ],
      hypotheses: [
        "Inter-service clock skew or network queue latency caused token to arrive after expiry boundary.",
        "Test fixture hardcodes short TTL (10s) that expired during test setup execution.",
      ],
      confidence: "High (94%)",
      recommendations: [
        "Configure leeway tolerance: jwt.decode(..., leeway=timedelta(seconds=30)).",
        "Ensure client refresh cycle initiates when 20% of TTL remains.",
        "Mock system time with freezegun or time-machine in pytest fixtures to eliminate flakiness.",
      ],
    },
    historicalMatches: [
      {
        id: "hist_cp_01",
        isCrossProject: true,
        sourceProject: "checkout-web",
        matchReason: "Identical PyJWT ExpiredSignatureError during microservice webhook invocation",
        sanitizedFixSummary: "Configured 30-second clock skew leeway on JWT decode options and synced container clock.",
        verified: true,
        fixOutcomeStatus: "VERIFIED",
      },
    ],
    fixOutcome: {
      status: "VERIFIED",
      proposedSolution: "Add leeway window (leeway=30s) to jwt.decode() and refresh token clock skew tolerance",
      verificationMethod: "devmemory run -- pytest tests/test_token_refresh.py -k test_clock_skew",
      testResult: "3 passed, 0 failed in 0.42s (exit code: 0)",
      recurrenceAfterFix: 0,
      verifiedAt: "2026-10-09T16:45:00Z",
    },
  },
  {
    incidentId: "inc_cuda_02",
    eventId: "evt_7d3c5d22",
    projectId: "proj_data_pipeline",
    projectName: "data-pipeline",
    timestamp: "2026-10-10T10:45:00Z",
    command: "python -m pipeline.preprocess --batch-size 128",
    exitCode: 137,
    errorType: "OutOfMemoryError (CUDA)",
    errorMessage: "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.40 GiB (GPU 0; 11.76 GiB total capacity; 9.82 GiB already allocated; 1.48 GiB free; 9.94 GiB reserved in total by PyTorch)",
    sourceLocation: {
      file: "pipeline/loader.py",
      line: 142,
      column: null,
      snippet: `138: def extract_features(dataloader, model, device):
139:     outputs = []
140:     for batch in dataloader:
141:         images = batch["images"].to(device, non_blocking=True)
142:         features = model.encoder(images)  # <-- CUDA Out of Memory
143:         outputs.append(features)
144:     return torch.cat(outputs, dim=0)`,
    },
    stackTrace: `Traceback (most recent call last):
  File "pipeline/preprocess.py", line 88, in <module>
    extract_features(loader, model, "cuda:0")
  File "pipeline/loader.py", line 142, in extract_features
    features = model.encoder(images)
  File "/usr/local/lib/python3.11/site-packages/torch/nn/modules/module.py", line 1501, in _call_impl
    return forward_call(*args, **kwargs)
torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.40 GiB`,
    aiDiagnosis: {
      observedEvidence: [
        "PyTorch requested 2.40 GiB contiguous allocation on GPU 0 with only 1.48 GiB unreserved memory remaining.",
        "Batch size set to 128 on 12 GiB VRAM GPU with fp32 precision.",
        "Accumulating raw 'features' tensors in Python list retains computational graph history in GPU memory.",
      ],
      hypotheses: [
        "Tensors appended to 'outputs' without '.detach().cpu()' prevent intermediate memory from being freed across batches.",
        "Batch size 128 exceeds maximum activation memory threshold for this model architecture.",
      ],
      confidence: "High (96%)",
      recommendations: [
        "Detach tensors and move to host memory: outputs.append(features.detach().cpu()).",
        "Wrap evaluation in 'with torch.no_grad():' context to disable gradient tracking graph.",
        "Reduce batch size to 64 or enable torch.cuda.amp.autocast() mixed precision.",
      ],
    },
    historicalMatches: [
      {
        id: "hist_proj_02",
        isCrossProject: false,
        sourceProject: "data-pipeline",
        matchReason: "Previous batch feature extraction failure in pipeline evaluation",
        sanitizedFixSummary: "Detached tensors to CPU memory and wrapped loop with torch.inference_mode().",
        verified: true,
        fixOutcomeStatus: "VERIFIED",
      },
    ],
    fixOutcome: {
      status: "PENDING",
      proposedSolution: "Add torch.inference_mode() and detach tensor features to CPU RAM immediately",
      verificationMethod: "devmemory run -- python -m pipeline.preprocess --eval-batch-memory",
      testResult: "Awaiting execution of verification command",
      recurrenceAfterFix: 0,
      verifiedAt: null,
    },
  },
  {
    incidentId: "inc_worker_03",
    eventId: "evt_3a1b2c3d",
    projectId: "proj_payment_worker",
    projectName: "payment-worker",
    timestamp: "2026-10-09T18:20:10Z",
    command: "npm test -- tests/idempotency.test.ts",
    exitCode: 1,
    errorType: "StripeIdempotencyKeyError",
    errorMessage: "StripeInvalidRequestError: Keys for idempotent requests can only be used with identical parameters. Parameter 'amount' changed from 4500 to 4550.",
    sourceLocation: {
      file: "services/stripeWebhook.ts",
      line: 67,
      column: 18,
      snippet: `65:     const idempotencyKey = \`checkout_\${userId}_\${Date.now()}\`;
66:     const charge = await stripe.charges.create({
67:       amount: req.body.amount,  // <-- Parameters diverged for replayed key
68:       currency: 'usd',
69:       customer: customerId,
70:     }, { idempotencyKey });`,
    },
    stackTrace: `StripeInvalidRequestError: Keys for idempotent requests can only be used with identical parameters.
    at StripeResource._makeRequest (/app/node_modules/stripe/lib/StripeResource.js:142:15)
    at processTicksAndRejections (node:internal/process/task_queues:95:5)
    at async processPayment (/app/services/stripeWebhook.ts:67:18)`,
    aiDiagnosis: {
      observedEvidence: [
        "Stripe rejected charge request due to parameter mismatch on active idempotency key.",
        "Idempotency key generation incorporates variable timestamp Date.now() instead of deterministic payload hash.",
      ],
      hypotheses: [
        "Client retried a failed payment after modifying cart items without acquiring a fresh order session ID.",
      ],
      confidence: "High (91%)",
      recommendations: [
        "Generate idempotency key by hashing order_id + line_items SHA-256.",
        "Never use timestamp or Date.now() in idempotency key strings.",
      ],
    },
    historicalMatches: [
      {
        id: "hist_cp_03",
        isCrossProject: true,
        sourceProject: "checkout-web",
        matchReason: "Cart replay caused idempotency conflict on Stripe SDK",
        sanitizedFixSummary: "Derived idempotency token from SHA-256 payload digest rather than timestamp.",
        verified: true,
        fixOutcomeStatus: "VERIFIED",
      },
    ],
    fixOutcome: {
      status: "VERIFIED",
      proposedSolution: "Generate deterministic SHA-256 idempotency key over order payload",
      verificationMethod: "devmemory run -- npm test -- tests/idempotency.test.ts",
      testResult: "5 passed, 0 failed in 0.38s",
      recurrenceAfterFix: 0,
      verifiedAt: "2026-10-09T19:30:00Z",
    },
  },
  {
    incidentId: "inc_sys_04",
    eventId: "evt_1f2e3d4c",
    projectId: "proj_payment_worker",
    projectName: "payment-worker",
    timestamp: "2026-10-08T15:10:00Z",
    command: "node --max-old-space-size=256 dist/worker.js",
    exitCode: 137,
    errorType: "SIGKILL (Container Out of Memory)",
    errorMessage: "Process terminated with exit code 137 by OS signal SIGKILL. Cgroup memory limit exceeded (256MB).",
    sourceLocation: null, // Test case: missing source code location handled safely!
    stackTrace: null,     // Test case: missing stack trace handled safely!
    aiDiagnosis: {
      observedEvidence: [
        "Process received external SIGKILL (128 + 9 = 137) from Linux cgroup OOM killer.",
        "No internal JavaScript V8 stack trace emitted because termination was abrupt from kernel space.",
        "Node flag set to strict 256MB old-space-size.",
      ],
      hypotheses: [
        "Unbounded batch job accumulated unprocessed webhook messages in memory during Redis surge.",
        "Buffer or native addon memory outside V8 heap exceeded container limit.",
      ],
      confidence: "Medium (78%)",
      recommendations: [
        "Throttle worker concurrency with backpressure (e.g. BullMQ rate limiter).",
        "Increase container memory allocation to at least 512MB.",
      ],
    },
    historicalMatches: [],
    fixOutcome: {
      status: "RECURRING",
      proposedSolution: "Increased container memory limit to 512MB and added BullMQ concurrency cap",
      verificationMethod: "devmemory run -- npm run test:load",
      testResult: "Process spiked again under 10k messages/sec surge",
      recurrenceAfterFix: 2,
      verifiedAt: null,
    },
  },
];

export const MOCK_PERFORMANCE_BY_PROJECT = {
  proj_auth_service: {
    projectId: "proj_auth_service",
    projectName: "auth-service",
    baselineMs: 130,
    medianMs: 145,
    tolerancePercent: 20,
    sampleCount: 8,
    runs: [
      { id: "r1", runIndex: 1, timestamp: "10:00", command: "pytest tests/test_auth.py", durationMs: 128, exitCode: 0, isRegression: false },
      { id: "r2", runIndex: 2, timestamp: "10:20", command: "pytest tests/test_auth.py", durationMs: 132, exitCode: 0, isRegression: false },
      { id: "r3", runIndex: 3, timestamp: "10:45", command: "pytest tests/test_auth.py", durationMs: 125, exitCode: 0, isRegression: false },
      { id: "r4", runIndex: 4, timestamp: "11:10", command: "pytest tests/test_auth.py", durationMs: 135, exitCode: 0, isRegression: false },
      { id: "r5", runIndex: 5, timestamp: "11:35", command: "pytest tests/test_auth.py", durationMs: 142, exitCode: 0, isRegression: false },
      { id: "r6", runIndex: 6, timestamp: "12:00", command: "pytest tests/test_token_refresh.py", durationMs: 290, exitCode: 0, isRegression: true, regressionDeltaMs: 160 },
      { id: "r7", runIndex: 7, timestamp: "12:15", command: "pytest tests/test_token_refresh.py -v", durationMs: 428, exitCode: 1, isRegression: true, regressionDeltaMs: 298 },
    ],
  },
  proj_data_pipeline: {
    projectId: "proj_data_pipeline",
    projectName: "data-pipeline",
    baselineMs: 1100,
    medianMs: 1420,
    tolerancePercent: 15,
    sampleCount: 6,
    runs: [
      { id: "p1", runIndex: 1, timestamp: "08:30", command: "python -m pipeline.preprocess", durationMs: 1080, exitCode: 0, isRegression: false },
      { id: "p2", runIndex: 2, timestamp: "09:00", command: "python -m pipeline.preprocess", durationMs: 1120, exitCode: 0, isRegression: false },
      { id: "p3", runIndex: 3, timestamp: "09:40", command: "python -m pipeline.preprocess", durationMs: 1150, exitCode: 0, isRegression: false },
      { id: "p4", runIndex: 4, timestamp: "10:10", command: "python -m pipeline.preprocess", durationMs: 1420, exitCode: 0, isRegression: true, regressionDeltaMs: 320 },
      { id: "p5", runIndex: 5, timestamp: "10:45", command: "python -m pipeline.preprocess --batch-size 128", durationMs: 2840, exitCode: 137, isRegression: true, regressionDeltaMs: 1740 },
    ],
  },
  proj_payment_worker: {
    projectId: "proj_payment_worker",
    projectName: "payment-worker",
    baselineMs: 315,
    medianMs: 310,
    tolerancePercent: 20,
    sampleCount: 4,
    runs: [
      { id: "w1", runIndex: 1, timestamp: "09:10", command: "npm test", durationMs: 305, exitCode: 0, isRegression: false },
      { id: "w2", runIndex: 2, timestamp: "10:30", command: "npm test", durationMs: 312, exitCode: 0, isRegression: false },
      { id: "w3", runIndex: 3, timestamp: "11:15", command: "npm test", durationMs: 318, exitCode: 0, isRegression: false },
      { id: "w4", runIndex: 4, timestamp: "11:58", command: "npm test -- tests/webhook.test.ts", durationMs: 295, exitCode: 0, isRegression: false },
    ],
  },
  proj_checkout_web: {
    projectId: "proj_checkout_web",
    projectName: "checkout-web",
    baselineMs: null,
    medianMs: null,
    tolerancePercent: 20,
    sampleCount: 0,
    runs: [], // Empty state test case!
  },
  proj_notification_service: {
    projectId: "proj_notification_service",
    projectName: "notification-service",
    baselineMs: 50,
    medianMs: 45,
    tolerancePercent: 20,
    sampleCount: 5,
    runs: [
      { id: "n1", runIndex: 1, timestamp: "11:00", command: "go test ./...", durationMs: 44, exitCode: 0, isRegression: false },
      { id: "n2", runIndex: 2, timestamp: "11:30", command: "go test ./...", durationMs: 46, exitCode: 0, isRegression: false },
      { id: "n3", runIndex: 3, timestamp: "12:00", command: "go test ./...", durationMs: 45, exitCode: 0, isRegression: false },
      { id: "n4", runIndex: 4, timestamp: "12:20", command: "go test ./...", durationMs: 48, exitCode: 0, isRegression: false },
      { id: "n5", runIndex: 5, timestamp: "12:30", command: "go test ./...", durationMs: 43, exitCode: 0, isRegression: false },
    ],
  },
};

export const MOCK_EVENTS = [
  {
    eventId: "evt_3f8c12a0",
    timestamp: "2026-10-10T12:30:00Z",
    projectId: "proj_notification_service",
    projectName: "notification-service",
    eventType: "COMMAND_RUN",
    status: "SUCCESS",
    summary: "go test ./cmd/dispatcher/... passed without regression",
    details: "Execution verified against 50ms baseline benchmark.",
    relatedCommand: "go test ./cmd/dispatcher/...",
    sourceLocation: { file: "cmd/dispatcher/main_test.go", line: 32 },
  },
  {
    eventId: "evt_9b1a7f40",
    timestamp: "2026-10-10T12:15:30Z",
    projectId: "proj_auth_service",
    projectName: "auth-service",
    eventType: "COMMAND_RUN",
    status: "FAILED",
    summary: "Command executed with exit code 1",
    relatedCommand: "pytest tests/test_token_refresh.py -v",
    relatedIncidentId: "inc_auth_01",
    sourceLocation: { file: "auth/tokens.py", line: 84, column: 12 },
    details: "Duration: 428ms. Raised ExpiredSignatureError in token validation",
  },
  {
    eventId: "evt_9b1a7f41",
    timestamp: "2026-10-10T12:15:35Z",
    projectId: "proj_auth_service",
    projectName: "auth-service",
    eventType: "AI_DIAGNOSIS",
    status: "RESOLVED",
    summary: "AI diagnosis generated with 94% confidence",
    relatedCommand: "pytest tests/test_token_refresh.py -v",
    relatedIncidentId: "inc_auth_01",
    sourceLocation: { file: "auth/tokens.py", line: 84, column: 12 },
    details: "Identified token expiration vs host clock skew; recommended leeway tolerance argument",
  },
  {
    eventId: "evt_8c2b6e31",
    timestamp: "2026-10-10T11:58:12Z",
    projectId: "proj_payment_worker",
    projectName: "payment-worker",
    eventType: "COMMAND_RUN",
    status: "SUCCESS",
    summary: "Test suite passed cleanly",
    relatedCommand: "npm test -- tests/webhook.test.ts",
    relatedIncidentId: null,
    sourceLocation: null,
    details: "Duration: 295ms. All webhook integration tests passed",
  },
  {
    eventId: "evt_7d3c5d22",
    timestamp: "2026-10-10T10:45:00Z",
    projectId: "proj_data_pipeline",
    projectName: "data-pipeline",
    eventType: "COMMAND_RUN",
    status: "FAILED",
    summary: "PyTorch CUDA allocation exceeded available VRAM",
    relatedCommand: "python -m pipeline.preprocess --batch-size 128",
    relatedIncidentId: "inc_cuda_02",
    sourceLocation: { file: "pipeline/loader.py", line: 142, column: null },
    details: "Exit code 137. OutOfMemoryError on GPU 0 while allocating 2.40 GiB",
  },
  {
    eventId: "evt_7d3c5d23",
    timestamp: "2026-10-10T10:45:10Z",
    projectId: "proj_data_pipeline",
    projectName: "data-pipeline",
    eventType: "PERFORMANCE_REGRESSION",
    status: "FLAGGED",
    summary: "Duration 2840ms exceeded baseline threshold (1100ms) by +158%",
    relatedCommand: "python -m pipeline.preprocess --batch-size 128",
    relatedIncidentId: "inc_cuda_02",
    sourceLocation: null,
    details: "Timing delta: +1740ms above established median benchmark",
  },
  {
    eventId: "evt_6e4d4c13",
    timestamp: "2026-10-10T09:30:21Z",
    projectId: "proj_checkout_web",
    projectName: "checkout-web",
    eventType: "COMMAND_RUN",
    status: "SUCCESS",
    summary: "Production bundle built successfully",
    relatedCommand: "npm run build",
    relatedIncidentId: null,
    sourceLocation: null,
    details: "Duration: 1420ms. Vite build finished with 0 errors",
  },
  {
    eventId: "evt_5f5e3b04",
    timestamp: "2026-10-09T19:30:00Z",
    projectId: "proj_payment_worker",
    projectName: "payment-worker",
    eventType: "FIX_VERIFICATION",
    status: "VERIFIED",
    summary: "Fix verified by passing test suite",
    relatedCommand: "npm test -- tests/idempotency.test.ts",
    relatedIncidentId: "inc_worker_03",
    sourceLocation: { file: "services/stripeWebhook.ts", line: 67, column: 18 },
    details: "Verified fix: SHA-256 payload digest prevents duplicate charge replays without recurrence",
  },
  {
    eventId: "evt_4a6f2a95",
    timestamp: "2026-10-08T15:10:00Z",
    projectId: "proj_payment_worker",
    projectName: "payment-worker",
    eventType: "FIX_VERIFICATION",
    status: "RECURRING",
    summary: "Verification failed under load; issue recurred 2x",
    relatedCommand: "npm run test:load",
    relatedIncidentId: "inc_sys_04",
    sourceLocation: null,
    details: "Container memory quota (512MB) was breached again during 10k req/s load test",
  },
];

