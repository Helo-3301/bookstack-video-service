/**
 * BSVS - BookStack Video Service Plugin
 *
 * This script adds video embedding functionality to BookStack's editor.
 * Add this to BookStack via Settings > Customization > Custom HTML Head Content.
 *
 * Usage:
 * <script>
 *   window.BSVS_URL = 'https://your-bsvs-server:8080';
 * </script>
 * <script src="https://your-bsvs-server:8080/static/js/bookstack-plugin.js"></script>
 */

(function() {
    'use strict';

    // Configuration
    const BSVS_URL = window.BSVS_URL || '';
    const STORAGE_KEY = 'bsvs_token';

    if (!BSVS_URL) {
        console.warn('BSVS: No BSVS_URL configured. Set window.BSVS_URL before loading this script.');
        return;
    }

    // Token management
    function getStoredToken() {
        return localStorage.getItem(STORAGE_KEY);
    }

    function storeToken(token) {
        localStorage.setItem(STORAGE_KEY, token);
    }

    function clearToken() {
        localStorage.removeItem(STORAGE_KEY);
    }

    function getAuthHeaders() {
        const token = getStoredToken();
        if (token) {
            return { 'Authorization': `Bearer ${token}` };
        }
        return {};
    }

    // Check if user can manage videos
    let userCanManageVideos = false;
    async function checkPermissions() {
        const token = getStoredToken();
        if (!token) {
            userCanManageVideos = false;
            return false;
        }

        try {
            const response = await fetch(`${BSVS_URL}/api/auth/me`, {
                headers: getAuthHeaders()
            });
            if (response.ok) {
                const data = await response.json();
                userCanManageVideos = data.can_manage_videos;
                return data.can_manage_videos;
            }
        } catch (error) {
            console.warn('BSVS: Permission check failed:', error);
        }
        userCanManageVideos = false;
        return false;
    }

    // Token setup modal
    function showTokenSetup() {
        const modal = document.createElement('div');
        modal.className = 'bsvs-modal-overlay';
        modal.innerHTML = `
            <div class="bsvs-modal" style="max-width: 450px;">
                <h2>BSVS Setup</h2>
                <p style="margin-bottom: 16px; color: #666;">
                    Enter your BookStack API token to manage videos.
                    You can create a token in your BookStack profile under "API Tokens".
                </p>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; margin-bottom: 6px; font-weight: 500;">API Token</label>
                    <input type="text" id="bsvs-token-input" placeholder="token_id:token_secret"
                           style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-family: monospace;">
                </div>
                <div class="bsvs-status" id="bsvs-token-status" style="margin-bottom: 16px;"></div>
                <div class="bsvs-modal-actions">
                    <button class="bsvs-btn bsvs-btn-secondary" id="bsvs-token-cancel">Cancel</button>
                    <button class="bsvs-btn bsvs-btn-primary" id="bsvs-token-save">Verify & Save</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const tokenInput = modal.querySelector('#bsvs-token-input');
        const statusEl = modal.querySelector('#bsvs-token-status');
        const saveBtn = modal.querySelector('#bsvs-token-save');
        const cancelBtn = modal.querySelector('#bsvs-token-cancel');

        // Pre-fill with existing token if any
        const existing = getStoredToken();
        if (existing) tokenInput.value = existing;

        cancelBtn.addEventListener('click', () => modal.remove());
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

        saveBtn.addEventListener('click', async () => {
            const token = tokenInput.value.trim();
            if (!token) {
                statusEl.textContent = 'Please enter a token';
                statusEl.style.color = '#d32f2f';
                return;
            }

            statusEl.textContent = 'Verifying...';
            statusEl.style.color = '#666';
            saveBtn.disabled = true;

            try {
                const response = await fetch(`${BSVS_URL}/api/auth/me`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.can_manage_videos) {
                        storeToken(token);
                        userCanManageVideos = true;
                        statusEl.textContent = `✓ Authenticated as ${data.user_name}`;
                        statusEl.style.color = '#2e7d32';
                        setTimeout(() => {
                            modal.remove();
                            updateMenuVisibility();
                        }, 1000);
                    } else {
                        statusEl.textContent = '✗ Token valid but you need Admin or Video Editor role';
                        statusEl.style.color = '#d32f2f';
                        saveBtn.disabled = false;
                    }
                } else {
                    statusEl.textContent = '✗ Invalid token';
                    statusEl.style.color = '#d32f2f';
                    saveBtn.disabled = false;
                }
            } catch (error) {
                statusEl.textContent = '✗ Connection error';
                statusEl.style.color = '#d32f2f';
                saveBtn.disabled = false;
            }
        });
    }

    // Styles for the modal
    const styles = `
        .bsvs-modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        }
        .bsvs-modal {
            background: white;
            border-radius: 8px;
            padding: 24px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }
        .bsvs-modal h2 {
            margin: 0 0 16px 0;
            font-size: 1.5rem;
        }
        .bsvs-modal-tabs {
            display: flex;
            border-bottom: 1px solid #ddd;
            margin-bottom: 16px;
        }
        .bsvs-modal-tab {
            padding: 8px 16px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
        }
        .bsvs-modal-tab.active {
            border-bottom-color: #1976d2;
            color: #1976d2;
        }
        .bsvs-tab-content {
            display: none;
        }
        .bsvs-tab-content.active {
            display: block;
        }
        .bsvs-upload-area {
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: border-color 0.3s;
        }
        .bsvs-upload-area:hover {
            border-color: #1976d2;
        }
        .bsvs-upload-area.dragover {
            border-color: #1976d2;
            background: #e3f2fd;
        }
        .bsvs-video-list {
            max-height: 300px;
            overflow-y: auto;
        }
        .bsvs-video-item {
            display: flex;
            align-items: center;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-bottom: 8px;
            cursor: pointer;
        }
        .bsvs-video-item:hover {
            background: #f5f5f5;
        }
        .bsvs-video-item.selected {
            border-color: #1976d2;
            background: #e3f2fd;
        }
        .bsvs-video-thumb {
            width: 80px;
            height: 45px;
            object-fit: cover;
            border-radius: 4px;
            margin-right: 12px;
            background: #eee;
        }
        .bsvs-video-info {
            flex: 1;
        }
        .bsvs-video-title {
            font-weight: 500;
        }
        .bsvs-video-meta {
            font-size: 0.85rem;
            color: #666;
        }
        .bsvs-btn {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
        }
        .bsvs-btn-primary {
            background: #1976d2;
            color: white;
        }
        .bsvs-btn-primary:hover {
            background: #1565c0;
        }
        .bsvs-btn-secondary {
            background: #e0e0e0;
            color: #333;
        }
        .bsvs-modal-actions {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            margin-top: 16px;
        }
        .bsvs-progress {
            width: 100%;
            height: 4px;
            background: #e0e0e0;
            border-radius: 2px;
            margin-top: 16px;
            overflow: hidden;
        }
        .bsvs-progress-bar {
            height: 100%;
            background: #1976d2;
            width: 0%;
            transition: width 0.3s;
        }
        .bsvs-status {
            margin-top: 8px;
            font-size: 0.9rem;
            color: #666;
        }
    `;

    // Inject styles
    const styleEl = document.createElement('style');
    styleEl.textContent = styles;
    document.head.appendChild(styleEl);

    // Modal HTML template
    function createModal() {
        const modal = document.createElement('div');
        modal.className = 'bsvs-modal-overlay';
        modal.innerHTML = `
            <div class="bsvs-modal">
                <h2>Insert Video</h2>
                <div class="bsvs-modal-tabs">
                    <div class="bsvs-modal-tab active" data-tab="upload">Upload New</div>
                    <div class="bsvs-modal-tab" data-tab="library">Video Library</div>
                </div>
                <div class="bsvs-tab-content active" data-tab="upload">
                    <div class="bsvs-upload-area" id="bsvs-upload-area">
                        <p>Drop a video file here or click to browse</p>
                        <input type="file" id="bsvs-file-input" accept="video/*" style="display: none;">
                    </div>
                    <div class="bsvs-progress" style="display: none;" id="bsvs-progress">
                        <div class="bsvs-progress-bar" id="bsvs-progress-bar"></div>
                    </div>
                    <div class="bsvs-status" id="bsvs-status"></div>
                </div>
                <div class="bsvs-tab-content" data-tab="library">
                    <div class="bsvs-video-list" id="bsvs-video-list">
                        <p>Loading videos...</p>
                    </div>
                </div>
                <div class="bsvs-modal-actions">
                    <button class="bsvs-btn bsvs-btn-secondary" id="bsvs-cancel">Cancel</button>
                    <button class="bsvs-btn bsvs-btn-primary" id="bsvs-insert" disabled>Insert Video</button>
                </div>
            </div>
        `;
        return modal;
    }

    // State
    let selectedVideoId = null;
    let modalEl = null;

    // API functions
    async function fetchVideos() {
        const response = await fetch(`${BSVS_URL}/api/videos`);
        if (!response.ok) throw new Error('Failed to fetch videos');
        return response.json();
    }

    async function fetchVideoInfo(videoId) {
        const response = await fetch(`${BSVS_URL}/api/videos/${videoId}`);
        if (!response.ok) throw new Error('Failed to fetch video info');
        return response.json();
    }

    async function requestViewerToken(videoId, pageId) {
        const response = await fetch(`${BSVS_URL}/api/auth/viewer-token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                video_id: videoId,
                page_id: pageId ? parseInt(pageId) : null,
            }),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Failed to get viewer token' }));
            throw new Error(error.detail || 'Failed to get viewer token');
        }

        return response.json();
    }

    async function uploadVideo(file) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('title', file.name.replace(/\.[^/.]+$/, ''));

        const response = await fetch(`${BSVS_URL}/api/videos`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: formData,
        });

        if (response.status === 401 || response.status === 403) {
            throw new Error('Authentication required. Please set up your API token.');
        }
        if (!response.ok) throw new Error('Upload failed');
        return response.json();
    }

    async function waitForReady(videoId, onProgress) {
        const maxAttempts = 120;  // 10 minutes max
        for (let i = 0; i < maxAttempts; i++) {
            const response = await fetch(`${BSVS_URL}/api/videos/${videoId}/status`);
            const data = await response.json();

            if (data.job) {
                onProgress(data.job.progress || 0, data.job.status);
            }

            if (data.status === 'ready') {
                return data;
            } else if (data.status === 'failed') {
                throw new Error('Video processing failed');
            }

            await new Promise(r => setTimeout(r, 5000));  // Poll every 5 seconds
        }
        throw new Error('Video processing timed out');
    }

    // Generate embed code - handles viewer tokens for protected videos
    async function generateEmbedCode(videoId, pageId) {
        try {
            // Fetch video info to check visibility
            const video = await fetchVideoInfo(videoId);
            const visibility = video.visibility || 'public';

            let embedUrl = `${BSVS_URL}/embed/${videoId}?`;
            const params = [];

            // Add page_id if available
            if (pageId) {
                params.push(`page_id=${pageId}`);
            }

            // For page_protected videos, get a viewer token
            if (visibility === 'page_protected') {
                try {
                    const tokenResponse = await requestViewerToken(videoId, pageId);
                    params.push(`vt=${encodeURIComponent(tokenResponse.token)}`);
                } catch (tokenError) {
                    console.warn('BSVS: Could not get viewer token:', tokenError.message);
                    // Still generate embed, player will show access denied
                }
            }

            embedUrl += params.join('&');

            return `<iframe src="${embedUrl}" width="100%" height="400" frameborder="0" allowfullscreen></iframe>`;
        } catch (error) {
            console.error('BSVS: Error generating embed code:', error);
            // Fallback to basic embed without token
            const pageParam = pageId ? `page_id=${pageId}` : '';
            return `<iframe src="${BSVS_URL}/embed/${videoId}?${pageParam}" width="100%" height="400" frameborder="0" allowfullscreen></iframe>`;
        }
    }

    // Synchronous version for simple cases
    function generateEmbedCodeSync(videoId, pageId) {
        const pageParam = pageId ? `page_id=${pageId}` : '';
        return `<iframe src="${BSVS_URL}/embed/${videoId}?${pageParam}" width="100%" height="400" frameborder="0" allowfullscreen></iframe>`;
    }

    // Get current page ID from BookStack
    function getCurrentPageId() {
        // Try to get page ID from URL or page meta
        const match = window.location.pathname.match(/\/pages\/(\d+)/);
        if (match) return match[1];

        const pageIdInput = document.querySelector('input[name="page_id"]');
        if (pageIdInput) return pageIdInput.value;

        return null;
    }

    // Insert embed code into editor
    function insertIntoEditor(embedCode) {
        // Try TinyMCE (BookStack WYSIWYG editor)
        if (window.tinymce && tinymce.activeEditor) {
            tinymce.activeEditor.insertContent(embedCode);
            return true;
        }

        // Try CodeMirror (Markdown editor)
        const cmElements = document.querySelectorAll('.CodeMirror');
        if (cmElements.length > 0) {
            const cm = cmElements[0].CodeMirror;
            if (cm) {
                const doc = cm.getDoc();
                doc.replaceSelection(embedCode);
                return true;
            }
        }

        // Fallback: try to find any textarea
        const textarea = document.querySelector('textarea[name="html"], textarea[name="markdown"]');
        if (textarea) {
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;
            textarea.value = textarea.value.substring(0, start) + embedCode + textarea.value.substring(end);
            return true;
        }

        return false;
    }

    // Modal functionality
    function openModal() {
        modalEl = createModal();
        document.body.appendChild(modalEl);
        selectedVideoId = null;

        // Tab switching
        modalEl.querySelectorAll('.bsvs-modal-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                modalEl.querySelectorAll('.bsvs-modal-tab').forEach(t => t.classList.remove('active'));
                modalEl.querySelectorAll('.bsvs-tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                modalEl.querySelector(`.bsvs-tab-content[data-tab="${tab.dataset.tab}"]`).classList.add('active');

                if (tab.dataset.tab === 'library') {
                    loadVideoLibrary();
                }
            });
        });

        // File upload
        const uploadArea = modalEl.querySelector('#bsvs-upload-area');
        const fileInput = modalEl.querySelector('#bsvs-file-input');

        uploadArea.addEventListener('click', () => fileInput.click());
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                handleFileUpload(e.dataTransfer.files[0]);
            }
        });
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                handleFileUpload(fileInput.files[0]);
            }
        });

        // Buttons
        modalEl.querySelector('#bsvs-cancel').addEventListener('click', closeModal);
        modalEl.querySelector('#bsvs-insert').addEventListener('click', async () => {
            if (selectedVideoId) {
                const insertBtn = modalEl.querySelector('#bsvs-insert');
                const statusEl = modalEl.querySelector('#bsvs-status');

                insertBtn.disabled = true;
                insertBtn.textContent = 'Generating...';
                if (statusEl) statusEl.textContent = 'Generating embed code...';

                try {
                    const pageId = getCurrentPageId();
                    const embedCode = await generateEmbedCode(selectedVideoId, pageId);

                    if (insertIntoEditor(embedCode)) {
                        closeModal();
                    } else {
                        // Show embed code for manual copy
                        alert('Embed code (copy and paste):\n\n' + embedCode);
                        closeModal();
                    }
                } catch (error) {
                    console.error('BSVS: Error inserting video:', error);
                    if (statusEl) statusEl.textContent = `Error: ${error.message}`;
                    insertBtn.disabled = false;
                    insertBtn.textContent = 'Insert Video';
                }
            }
        });

        // Close on overlay click
        modalEl.addEventListener('click', (e) => {
            if (e.target === modalEl) closeModal();
        });
    }

    function closeModal() {
        if (modalEl) {
            modalEl.remove();
            modalEl = null;
        }
    }

    async function handleFileUpload(file) {
        const progressEl = modalEl.querySelector('#bsvs-progress');
        const progressBar = modalEl.querySelector('#bsvs-progress-bar');
        const statusEl = modalEl.querySelector('#bsvs-status');
        const insertBtn = modalEl.querySelector('#bsvs-insert');

        progressEl.style.display = 'block';
        statusEl.textContent = 'Uploading...';
        progressBar.style.width = '10%';

        try {
            const video = await uploadVideo(file);
            statusEl.textContent = 'Processing video...';
            progressBar.style.width = '30%';

            await waitForReady(video.id, (progress, status) => {
                progressBar.style.width = `${30 + (progress * 0.7)}%`;
                statusEl.textContent = `Processing: ${progress}%`;
            });

            progressBar.style.width = '100%';
            statusEl.textContent = 'Video ready!';
            selectedVideoId = video.id;
            insertBtn.disabled = false;
        } catch (error) {
            statusEl.textContent = `Error: ${error.message}`;
            progressBar.style.width = '0%';
        }
    }

    async function loadVideoLibrary() {
        const listEl = modalEl.querySelector('#bsvs-video-list');
        const insertBtn = modalEl.querySelector('#bsvs-insert');

        try {
            const data = await fetchVideos();
            if (data.videos.length === 0) {
                listEl.innerHTML = '<p>No videos uploaded yet.</p>';
                return;
            }

            listEl.innerHTML = data.videos
                .filter(v => v.status === 'ready')
                .map(v => {
                    const visibilityBadge = getVisibilityBadge(v.visibility || 'public');
                    return `
                    <div class="bsvs-video-item" data-id="${v.id}">
                        <img class="bsvs-video-thumb" src="${BSVS_URL}/stream/${v.id}/thumbnail.jpg" alt="">
                        <div class="bsvs-video-info">
                            <div class="bsvs-video-title">${escapeHtml(v.title)}</div>
                            <div class="bsvs-video-meta">
                                ${v.duration_seconds ? formatDuration(v.duration_seconds) : 'Unknown duration'}
                                ${visibilityBadge}
                            </div>
                        </div>
                    </div>
                    `;
                }).join('');

            listEl.querySelectorAll('.bsvs-video-item').forEach(item => {
                item.addEventListener('click', () => {
                    listEl.querySelectorAll('.bsvs-video-item').forEach(i => i.classList.remove('selected'));
                    item.classList.add('selected');
                    selectedVideoId = item.dataset.id;
                    insertBtn.disabled = false;
                });
            });
        } catch (error) {
            listEl.innerHTML = `<p>Error loading videos: ${error.message}</p>`;
        }
    }

    // Helpers
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatDuration(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    function getVisibilityBadge(visibility) {
        const badges = {
            'public': '<span style="background:#4caf50;color:white;padding:2px 6px;border-radius:3px;font-size:0.75rem;margin-left:8px;">Public</span>',
            'unlisted': '<span style="background:#ff9800;color:white;padding:2px 6px;border-radius:3px;font-size:0.75rem;margin-left:8px;">Unlisted</span>',
            'page_protected': '<span style="background:#2196f3;color:white;padding:2px 6px;border-radius:3px;font-size:0.75rem;margin-left:8px;">Protected</span>',
            'private': '<span style="background:#f44336;color:white;padding:2px 6px;border-radius:3px;font-size:0.75rem;margin-left:8px;">Private</span>',
        };
        return badges[visibility] || '';
    }

    // Add button to BookStack editor toolbar
    function addToolbarButton() {
        // Wait for editor to load
        const observer = new MutationObserver(() => {
            // Look for TinyMCE toolbar
            const toolbar = document.querySelector('.tox-toolbar__primary, .editor-toolbar');
            if (toolbar && !toolbar.querySelector('.bsvs-toolbar-btn')) {
                const btn = document.createElement('button');
                btn.className = 'bsvs-toolbar-btn tox-tbtn';
                btn.innerHTML = '<span style="font-size: 14px;">🎬</span>';
                btn.title = 'Insert Video (BSVS)';
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    openModal();
                });
                toolbar.appendChild(btn);
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });

        // Also try immediately
        setTimeout(() => {
            const toolbar = document.querySelector('.tox-toolbar__primary, .editor-toolbar');
            if (toolbar && !toolbar.querySelector('.bsvs-toolbar-btn')) {
                const btn = document.createElement('button');
                btn.className = 'bsvs-toolbar-btn tox-tbtn';
                btn.innerHTML = '<span style="font-size: 14px;">🎬</span>';
                btn.title = 'Insert Video (BSVS)';
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    openModal();
                });
                toolbar.appendChild(btn);
            }
        }, 2000);
    }

    // Add BSVS menu to BookStack header
    let headerMenuEl = null;

    function isBookStackUserLoggedIn() {
        // Check if we're on the login page
        if (window.location.pathname === '/login') {
            return false;
        }
        // Check for login link in header (indicates user is NOT logged in)
        const loginLink = document.querySelector('a[href*="/login"]');
        if (loginLink && loginLink.closest('header, nav, .header-links')) {
            return false;
        }
        // Check for user menu (indicates user IS logged in)
        const userMenu = document.querySelector('.user-name, .dropdown-toggle .avatar, [data-user-profile]');
        if (userMenu) {
            return true;
        }
        // Default: assume logged in if not on login page and no login link found
        return !document.querySelector('form[action*="login"]');
    }

    function addHeaderMenu() {
        // Only show menu if user is logged into BookStack
        if (!isBookStackUserLoggedIn()) {
            // Remove menu if it exists (in case page state changed)
            const existingMenu = document.querySelector('.bsvs-header-menu');
            if (existingMenu) {
                existingMenu.remove();
            }
            return;
        }

        // Find BookStack header actions area
        const headerRight = document.querySelector('.header-links, .header-right, header .actions');
        if (headerRight && !document.querySelector('.bsvs-header-menu')) {
            const menuContainer = document.createElement('div');
            menuContainer.className = 'bsvs-header-menu';
            menuContainer.style.cssText = 'display: inline-flex; align-items: center; margin-left: 10px;';
            menuContainer.innerHTML = `
                <div class="dropdown-container" style="position: relative;">
                    <button class="bsvs-menu-btn" style="
                        background: none;
                        border: 1px solid rgba(255,255,255,0.3);
                        border-radius: 4px;
                        color: inherit;
                        padding: 6px 12px;
                        cursor: pointer;
                        font-size: 14px;
                        display: flex;
                        align-items: center;
                        gap: 6px;
                    ">
                        🎬 Videos
                    </button>
                    <div class="bsvs-dropdown" style="
                        display: none;
                        position: absolute;
                        right: 0;
                        top: 100%;
                        background: white;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                        min-width: 180px;
                        z-index: 1000;
                    ">
                        <a href="${BSVS_URL}/" target="_blank" class="bsvs-menu-item bsvs-requires-auth" style="
                            display: block;
                            padding: 10px 16px;
                            color: #333;
                            text-decoration: none;
                            border-bottom: 1px solid #eee;
                        ">📤 Upload Video</a>
                        <a href="${BSVS_URL}/admin" target="_blank" class="bsvs-menu-item bsvs-requires-auth" style="
                            display: block;
                            padding: 10px 16px;
                            color: #333;
                            text-decoration: none;
                            border-bottom: 1px solid #eee;
                        ">⚙️ Video Admin</a>
                        <a href="#" class="bsvs-menu-item bsvs-setup-link" style="
                            display: block;
                            padding: 10px 16px;
                            color: #333;
                            text-decoration: none;
                        ">🔑 Setup API Token</a>
                    </div>
                </div>
            `;

            // Toggle dropdown
            const btn = menuContainer.querySelector('.bsvs-menu-btn');
            const dropdown = menuContainer.querySelector('.bsvs-dropdown');
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
            });

            // Close on outside click
            document.addEventListener('click', () => {
                dropdown.style.display = 'none';
            });

            // Hover effects for links
            dropdown.querySelectorAll('a').forEach(link => {
                link.addEventListener('mouseenter', () => link.style.background = '#f5f5f5');
                link.addEventListener('mouseleave', () => link.style.background = 'white');
            });

            // Setup link click
            menuContainer.querySelector('.bsvs-setup-link').addEventListener('click', (e) => {
                e.preventDefault();
                dropdown.style.display = 'none';
                showTokenSetup();
            });

            headerRight.appendChild(menuContainer);
            headerMenuEl = menuContainer;

            // Update visibility based on permissions
            updateMenuVisibility();
        }
    }

    function updateMenuVisibility() {
        if (!headerMenuEl) return;

        const authItems = headerMenuEl.querySelectorAll('.bsvs-requires-auth');
        const setupLink = headerMenuEl.querySelector('.bsvs-setup-link');

        if (userCanManageVideos) {
            // User has permission - show upload/admin, change setup to "Change Token"
            authItems.forEach(item => item.style.display = 'block');
            setupLink.textContent = '🔑 Change API Token';
        } else {
            // User doesn't have permission - hide upload/admin, show setup
            authItems.forEach(item => item.style.display = 'none');
            setupLink.textContent = '🔑 Setup API Token';
        }
    }

    // Initialize when DOM is ready
    async function init() {
        // Check permissions first
        await checkPermissions();

        addToolbarButton();
        addHeaderMenu();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose API for manual use
    window.BSVS = {
        openModal,
        generateEmbedCode,
        BSVS_URL
    };

    console.log('BSVS: BookStack Video Service plugin loaded');
})();
