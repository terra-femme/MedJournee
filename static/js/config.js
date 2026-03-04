// API Configuration for MedJournee
// AUTO-DETECTS the environment based on how you access the app

const API_CONFIG = {
    LOCAL: 'http://localhost:8000',
    TAILSCALE: 'https://terra.tail8736aa.ts.net',
    RENDER: 'https://your-app.onrender.com'
};

// AUTO-DETECT: Checks the URL in the browser address bar
function detectEnvironment() {
    const hostname = window.location.hostname;
    const port = window.location.port;

    // If accessed via localhost or 127.0.0.1 → use local API
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return API_CONFIG.LOCAL;
    }

    // If accessed via Tailscale hostname → use Tailscale API
    if (hostname.includes('tail8736aa.ts.net')) {
        return API_CONFIG.TAILSCALE;
    }

    // If accessed via Render hostname → use Render API
    if (hostname.includes('onrender.com')) {
        return API_CONFIG.RENDER;
    }

    // Default fallback (shouldn't happen)
    console.warn('[Config] Unknown hostname:', hostname, '- using LOCAL');
    return API_CONFIG.LOCAL;
}

// Set API_BASE based on auto-detection
const API_BASE = detectEnvironment();

// Log which environment is being used (check browser console F12)
console.log('[Config] Environment detected:', window.location.hostname);
console.log('[Config] API_BASE set to:', API_BASE);
