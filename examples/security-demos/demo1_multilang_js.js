/**
 * DevMemory Demo 1 (JavaScript / Node.js): Multi-Language Diagnostic Demonstration.
 *
 * Demonstrates DevMemory's language-independent diagnostic parsing for Node.js runtimes.
 *
 * Usage:
 *     devmemory run -- node demo1_multilang_js.js
 */

function processUserSession(session) {
    console.log("[Demo 1 - Node.js] Processing active user session...");
    // Intentional TypeError: Cannot read properties of undefined (reading 'token')
    const authToken = session.auth.token;
    console.log(`Authenticated with token: ${authToken}`);
}

function main() {
    console.log("[Demo 1 - Node.js] Initializing session handler...");
    const uninitializedSession = undefined;
    processUserSession(uninitializedSession);
}

main();
