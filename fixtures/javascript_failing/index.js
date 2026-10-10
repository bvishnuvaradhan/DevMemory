/**
 * Deterministic JavaScript failure fixture for DevMemory end-to-end testing.
 * Throws a TypeError accessing a nested property on undefined.
 */

function getUserProfile(user) {
    // Explicit failing operation on line 8
    return user.profile.settings.theme;
}

function renderDashboard(session) {
    console.log("Rendering dashboard for session:", session.sessionId);
    return getUserProfile(session.user);
}

const activeSession = {
    sessionId: "sess_4815162342",
    user: undefined
};

renderDashboard(activeSession);
