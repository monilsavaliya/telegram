const PHONE_NUMBER = "919328552413"; // Simulated User Number

// DOM Elements
const chatInput = document.getElementById('message-input');
const messageList = document.getElementById('message-list');
const attachmentMenu = document.getElementById('attachment-menu');
const attachBtn = document.getElementById('attach-btn');

// Toggle Attachment Menu
attachBtn.addEventListener('click', () => {
    attachmentMenu.classList.toggle('active');
});

// Sidebar Toggle Logic (New)
// Sidebar Toggle Logic
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebar = document.querySelector('.sidebar');

if (sidebarToggle && sidebar) {
    // Load State
    // If localStorage has 'false', it means user Opened it.
    // If 'true' or null (default), we keep it collapsed (HTML default).
    const isCollapsed = localStorage.getItem('sidebarCollapsed');

    if (isCollapsed === 'false') {
        sidebar.classList.remove('collapsed');
    } else {
        // Ensure it's collapsed (redundant if HTML has it, but good for safety)
        sidebar.classList.add('collapsed');
    }

    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        // Save State
        localStorage.setItem('sidebarState_v2', sidebar.classList.contains('collapsed'));
    });
}

// Close menu when clicking outside
document.addEventListener('click', (e) => {
    if (!attachBtn.contains(e.target) && !attachmentMenu.contains(e.target)) {
        attachmentMenu.classList.remove('active');
    }
});

// Handle Enter Key
chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

// --- Core Logic ---

async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = '';

    // UI Update
    addMessageToUI('text', text, true);

    // Status Feedback
    document.querySelector('.chat-status').innerText = 'thinking...';

    // Payload Construction
    const payload = constructMetaPayload('text', { body: text });

    // Send to Backend
    await sendToBackend(payload);
}

function addMessageToUI(type, content, isSent) {
    const div = document.createElement('div');
    div.className = `message ${isSent ? 'sent' : 'received'}`;

    let innerContent = '';
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (type === 'text') {
        // Use innerHTML to render <br> and <a> tags from linkify
        div.innerHTML = `
            <div class="bubble">
                ${content} 
                <span class="meta">${time} ${isSent ? '<i class="ph ph-check"></i>' : ''}</span>
            </div>
        `;
    } else {
        // Other types (image, location etc) use this wrapper logic
        div.innerHTML = `
            <div class="bubble">
                ${innerContent}
                <span class="meta">${time} ${isSent ? '<i class="ph ph-check"></i>' : ''}</span>
            </div>
        `;
    }

    messageList.appendChild(div);
    scrollToBottom();

    // Hook for Infinite Scroll
    const loader = div.querySelector('.carousel-loader');
    if (loader) {
        carouselObserver.observe(loader);
    }
}

function scrollToBottom() {
    messageList.scrollTop = messageList.scrollHeight;
}

// --- Attachment Handlers ---

function sendLocation() {
    attachmentMenu.classList.remove('active');
    if (!navigator.geolocation) return alert("Geolocation not supported");

    addMessageToUI('text', '📍 Fetching location...', true);

    navigator.geolocation.getCurrentPosition(async (position) => {
        const { latitude, longitude } = position.coords;
        addMessageToUI('location', { lat: latitude, long: longitude }, true);

        const payload = constructMetaPayload('location', {
            latitude: latitude,
            longitude: longitude
        });
        await sendToBackend(payload);
    });
}

function handleFileSelect(input, type) {
    attachmentMenu.classList.remove('active');
    const file = input.files[0];
    if (!file) return;

    // Create a local preview URL
    const url = URL.createObjectURL(file);
    addMessageToUI(type, url, true);

    // Convert to Base64 for Simulation Transfer
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = function () {
        const base64Data = reader.result; // This includes "data:image/png;base64,..."

        // Construct Payload with REAL DATA
        const payload = constructMetaPayload(type, {
            id: "media_" + Date.now(),
            caption: "Attached Media",
            mime_type: file.type,
            data: base64Data // Sending actual bytes (Base64) to backend
        });

        sendToBackend(payload);
    };
}

// --- Audio Recorder Mock ---
function toggleAudioRecorder() {
    attachmentMenu.classList.remove('active');
    document.getElementById('audio-recorder').classList.remove('hidden');
}

function cancelAudio() {
    document.getElementById('audio-recorder').classList.add('hidden');
}

function sendAudioMock() {
    document.getElementById('audio-recorder').classList.add('hidden');
    addMessageToUI('audio', null, true);
    // Send dummy audio payload
    const payload = constructMetaPayload('audio', { id: "audio_123" });
    sendToBackend(payload);
}

// --- Backend Communication ---

function constructMetaPayload(type, data) {
    // Mimics the WhatsApp Cloud API Webhook structure
    return {
        object: "whatsapp_business_account",
        entry: [{
            changes: [{
                value: {
                    messages: [{
                        from: PHONE_NUMBER,
                        id: "wamid.test_" + Date.now(),
                        timestamp: Math.floor(Date.now() / 1000),
                        type: type,
                        [type]: data
                    }]
                }
            }]
        }]
    };
}

async function sendToBackend(jsonPayload) {
    try {
        await fetch('/simulate/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(jsonPayload)
        });
        // In simulation, we immediately mark as delivered/read (visual only)
        const sentChecks = document.querySelectorAll('.message.sent .ph-check');
        if (sentChecks.length) sentChecks[sentChecks.length - 1].className = "ph ph-checks";
    } catch (e) {
        console.error("Simulation Error:", e);
    }
}

// --- Polling for Replies ---
setInterval(async () => {
    try {
        const res = await fetch(`/simulate/poll?phone=${PHONE_NUMBER}`);
        const messages = await res.json();

        if (messages.length > 0) {
            const statusEl = document.querySelector('.chat-status');
            statusEl.innerText = 'typing...';
            statusEl.classList.add('typing');

            setTimeout(() => {
                statusEl.innerText = 'online';
                statusEl.classList.remove('typing');
                messages.forEach(msg => {
                    // msg is { text: "..." }
                    let content = msg.text.body;

                    // Check if it's a Rich HTML Card (starts with unique class)
                    // relaxing the check to ensure whitespace doesn't break it
                    if (content.includes('data-exclude-linkify="true"')) {
                        // Render directly (Trusted HTML from Backend)
                        addMessageToUI('text', content, false);
                    } else {
                        // Standard Text -> Linkify
                        const safeText = content.replace(/\n/g, '<br>');
                        const linkedText = linkify(safeText);
                        addMessageToUI('text', linkedText, false);
                    }
                });
                // Play notification sound?
            }, 800); // Fake typing delay
        }
    } catch (e) {
        // console.error(e);
    }
}, 1000);

// Helper to make links clickable
// Helper to make links clickable (Supports Markdown [Text](Link))
function linkify(inputText) {
    let replacedText = inputText;

    // 1. Markdown Links: [Link Text](URL) -> <a href="URL" ...>Link Text</a>
    const mdPattern = /\[(.*?)\]\((.*?)\)/gim;
    replacedText = replacedText.replace(mdPattern, '<a href="$2" target="_blank" style="color: var(--accent); text-decoration: none; font-weight: bold;">$1 <i class="ph ph-arrow-square-out"></i></a>');

    // 2. Standard URLs (http/https/ftp) - reduced greediness to avoid breaking MD links if they overlap (though MD runs first)
    // We use a negative lookbehind to ensure we don't double-link strings already inside quotes or tags
    const urlPattern = /(\b(https?|ftp):\/\/[-A-Z0-9+&@#\/%?=~_|!:,.;]*[-A-Z0-9+&@#\/%=~_|])/gim;

    // Simple verification to prevent double-linking:
    // This simple regex might re-link, but since we ran MD first, we should be okay if we assume MD links don't contain raw URLs as text.
    // Ideally we'd use a parser, but for this snippet:

    // Only linkify if NOT inside an HTML tag (simple hack)
    // ...Skipping complex regex. Assuming Backend sends MD links primarily.

    // Fallback for raw URLs that weren't MD formatted
    replacedText = replacedText.replace(urlPattern, (match) => {
        // If match is part of <a href="...">, ignore. 
        if (replacedText.includes(`href="${match}"`)) return match;
        return `<a href="${match}" target="_blank">${match}</a>`;
    });

    return replacedText;
}

// --- INFINITE SCROLL LOGIC ---
const observerOptions = {
    root: null, // viewport
    rootMargin: '100px', // Pre-fetch before user hits the very edge
    threshold: 0.1
};

const carouselObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const loader = entry.target;
            fetchMoreItems(loader);
            carouselObserver.unobserve(loader); // Prevent double trigger
        }
    });
}, observerOptions);

async function fetchMoreItems(loader) {
    const type = loader.dataset.type;
    const query = loader.dataset.query;
    const page = loader.dataset.page;
    const container = loader.parentElement;

    try {
        console.log(`Fetching more ${type} page ${page}...`);
        const res = await fetch(`/api/fetch_more?type=${type}&query=${query}&page=${page}`);
        const data = await res.json();

        // Remove current loader
        loader.remove();

        if (data.html) {
            // Append new items
            // We need to insert HTML string as nodes before the end
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = data.html;

            // Move children to main container
            while (tempDiv.firstChild) {
                const child = tempDiv.firstChild;
                container.appendChild(child);

                // If new loader exists, observe it
                if (child.classList && child.classList.contains('carousel-loader')) {
                    carouselObserver.observe(child);
                }
            }
        }
    } catch (e) {
        console.error("Infinite Scroll Error:", e);
        loader.innerHTML = '⚠️';
    }
}
