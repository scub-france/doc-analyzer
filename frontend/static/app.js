// DocTags Application State Management
const appState = {
    activeTasks: {},
    pollingInterval: null,
    generatedOutputs: {
        visualizer: null,
        extractor: false
    }
};

// API Client
const api = {
    async get(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
    },

    async post(url, formData) {
        const response = await fetch(url, { method: 'POST', body: formData });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
    }
};

// UI Helper Functions
const ui = {
    show(elementId) {
        document.getElementById(elementId).classList.remove('hidden');
    },

    hide(elementId) {
        document.getElementById(elementId).classList.add('hidden');
    },

    setText(elementId, text) {
        document.getElementById(elementId).textContent = text;
    },

    setHtml(elementId, html) {
        document.getElementById(elementId).innerHTML = html;
    },

    getValue(elementId) {
        return document.getElementById(elementId).value;
    },

    setValue(elementId, value) {
        document.getElementById(elementId).value = value;
    },

    disable(elementId) {
        document.getElementById(elementId).disabled = true;
    },

    enable(elementId) {
        document.getElementById(elementId).disabled = false;
    }
};

// PDF Preview Functions
function loadPDFPreview() {
    const pdfFile = ui.getValue('pdf_file');
    const pageNum = ui.getValue('page_num');

    if (!pdfFile) {
        ui.hide('pdf-preview-container');
        return;
    }

    ui.setText('preview-page-num', pageNum);
    ui.setValue('preview-page-input', pageNum);

    const previewImg = document.getElementById('pdf-preview-image');
    previewImg.src = `/pdf-preview/${encodeURIComponent(pdfFile)}/${pageNum}`;
    ui.show('pdf-preview-container');

    previewImg.onerror = function() {
        this.alt = 'Failed to load PDF preview';
        console.error('Failed to load PDF preview');
    };
}

function changePreviewPage(delta) {
    const currentPage = parseInt(ui.getValue('page_num'));
    const newPage = Math.max(1, currentPage + delta);
    ui.setValue('page_num', newPage);
    loadPDFPreview();
}

function goToPreviewPage() {
    const pageInput = document.getElementById('preview-page-input');
    const pageNum = parseInt(pageInput.value);

    if (pageNum && pageNum > 0) {
        ui.setValue('page_num', pageNum);
        loadPDFPreview();
    } else {
        pageInput.value = ui.getValue('page_num');
    }
}

// Tab Management
function switchTab(tabName) {
    // Hide all tab contents and deactivate buttons
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.querySelectorAll('.tab-button').forEach(button => button.classList.remove('active'));

    // Show selected tab
    document.getElementById(tabName + '-tab').classList.add('active');
    event.target.classList.add('active');

    // Show previously generated content
    if (tabName === 'analyzer') {
        loadPDFPreview();
    } else if (tabName === 'visualizer' && appState.generatedOutputs.visualizer) {
        document.getElementById('result-image').src = appState.generatedOutputs.visualizer + '?t=' + Date.now();
        ui.show('image-container');
    } else if (tabName === 'extractor' && appState.generatedOutputs.extractor) {
        loadExtractedImages();
    }
}

// Progress Management
function updateProgress(completedSteps) {
    for (let i = 1; i <= 3; i++) {
        const stepIndicator = document.getElementById(`step-${i}`);
        const connector = document.getElementById(`connector-${i}`);

        if (i <= completedSteps) {
            stepIndicator.classList.add('completed');
            stepIndicator.classList.remove('active');
            if (connector) connector.classList.add('completed');
        } else if (i === completedSteps + 1) {
            stepIndicator.classList.add('active');
            stepIndicator.classList.remove('completed');
        } else {
            stepIndicator.classList.remove('completed', 'active');
            if (connector) connector.classList.remove('completed');
        }
    }
}

// Task Management
function startPolling() {
    if (!appState.pollingInterval) {
        appState.pollingInterval = setInterval(pollTasks, 1000);
    }
}

function stopPolling() {
    if (Object.keys(appState.activeTasks).length === 0 && appState.pollingInterval) {
        clearInterval(appState.pollingInterval);
        appState.pollingInterval = null;
    }
}

async function pollTasks() {
    for (const taskId in appState.activeTasks) {
        try {
            const data = await api.get(`/task-status/${taskId}`);
            updateTaskStatus(taskId, data);
        } catch (error) {
            console.error('Error polling task:', error);
        }
    }
}

function updateTaskStatus(taskId, data) {
    const taskInfo = appState.activeTasks[taskId];
    const statusElement = document.getElementById(`${taskInfo.type}-status`);

    if (data.done) {
        if (data.success) {
            handleTaskSuccess(taskId, taskInfo, data, statusElement);
        } else {
            handleTaskFailure(taskId, data, statusElement);
        }
        delete appState.activeTasks[taskId];
        stopPolling();
    } else {
        ui.setHtml(statusElement, '<div class="loader"></div><span class="working">Running...</span>');
        ui.show(statusElement.id);
    }
}

function handleTaskSuccess(taskId, taskInfo, data, statusElement) {
    ui.setHtml(statusElement, '<span class="success">✓ Completed successfully!</span>');
    ui.show(statusElement.id);
    ui.enable(`${taskInfo.type}-btn`);

    // Display output
    ui.setText('output', data.output);
    ui.show('output');

    // Handle specific task types
    if (taskInfo.type === 'visualizer' && data.image_file) {
        appState.generatedOutputs.visualizer = '/' + data.image_file;
        document.getElementById('result-image').src = appState.generatedOutputs.visualizer + '?t=' + Date.now();
        ui.show('image-container');
    } else if (taskInfo.type === 'extractor') {
        setTimeout(loadExtractedImages, 1000);
    }

    // Update progress
    const progressMap = { 'analyzer': 1, 'visualizer': 2, 'extractor': 3 };
    updateProgress(progressMap[taskInfo.type]);

    // Enable next steps
    if (taskInfo.type === 'analyzer') {
        ui.enable('visualizer-btn');
    } else if (taskInfo.type === 'visualizer') {
        ui.enable('extractor-btn');
    }
}

function handleTaskFailure(taskId, data, statusElement) {
    ui.setHtml(statusElement, '<span class="error">✗ Failed: ' + (data.error || 'Unknown error') + '</span>');
    ui.show(statusElement.id);
    ui.enable(statusElement.id.replace('-status', '-btn'));

    ui.setText('output', 'Error: ' + (data.error || 'Unknown error'));
    ui.show('output');
}

// Script Execution
async function runScript(script) {
    const pdfFile = ui.getValue('pdf_file');
    const pageNum = ui.getValue('page_num');
    const adjust = document.getElementById('adjust').checked;

    if (!pdfFile) {
        alert('Please select a PDF file');
        return;
    }

    // Disable button and show status
    ui.disable(`${script}-btn`);
    ui.setHtml(`${script}-status`, '<div class="loader"></div><span class="working">Starting...</span>');
    ui.show(`${script}-status`);
    ui.hide('output');

    // Reset outputs for analyzer
    if (script === 'analyzer') {
        ui.hide('image-container');
        ui.hide('extracted-images-container');
        appState.generatedOutputs = { visualizer: null, extractor: false };
        ui.disable('visualizer-btn');
        ui.disable('extractor-btn');
        updateProgress(0);
    }

    // Create form data
    const formData = new FormData();
    formData.append('pdf_file', pdfFile);
    formData.append('page_num', pageNum);
    formData.append('adjust', adjust);

    try {
        const data = await api.post(`/run-${script}`, formData);

        if (data.success && data.task_id) {
            appState.activeTasks[data.task_id] = {
                type: script,
                pageNum: pageNum
            };
            startPolling();

            ui.setText('output', data.message || 'Task started, please wait...');
            ui.show('output');
        } else {
            throw new Error(data.error || 'Failed to start task');
        }
    } catch (error) {
        ui.setHtml(`${script}-status`, '<span class="error">✗ ' + error.message + '</span>');
        ui.enable(`${script}-btn`);
        ui.setText('output', 'Error: ' + error.message);
        ui.show('output');
    }
}

// Image Gallery Functions
async function loadExtractedImages() {
    const imageGallery = document.getElementById('extracted-images-gallery');

    try {
        const response = await fetch('/results/pictures/index.html');
        if (!response.ok) throw new Error('No extracted images found');

        const html = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const imageCards = doc.querySelectorAll('.picture-card');

        if (imageCards.length === 0) {
            imageGallery.innerHTML = '<div class="no-images">No images were extracted from this page.</div>';
            return;
        }

        let galleryHTML = '';
        imageCards.forEach((card, index) => {
            const img = card.querySelector('img');
            const caption = card.querySelector('.picture-caption');
            const coords = card.querySelector('.picture-coords');

            if (img) {
                const imgSrc = img.getAttribute('src');
                const pictureId = index + 1;
                const captionText = caption ? caption.textContent : '';
                const coordsText = coords ? coords.textContent : '';

                galleryHTML += `
                    <div class="extracted-image-card">
                        <div class="image-wrapper">
                            <img src="/results/pictures/${imgSrc}" alt="Extracted Image ${pictureId}" 
                                 onclick="openImageModal('/results/pictures/${imgSrc}', '${captionText}', '${coordsText}')">
                        </div>
                        <div class="image-info">
                            <h4>Picture ${pictureId}</h4>
                            ${captionText ? `<p class="image-caption">${captionText}</p>` : ''}
                            <p class="image-coords">${coordsText}</p>
                        </div>
                    </div>
                `;
            }
        });

        imageGallery.innerHTML = galleryHTML;
        ui.show('extracted-images-container');
        appState.generatedOutputs.extractor = true;
    } catch (error) {
        console.log('No extracted images found:', error);
        imageGallery.innerHTML = '<div class="no-images">No images have been extracted yet. Run the image extraction first.</div>';
        appState.generatedOutputs.extractor = false;
    }
}

// Modal Functions
function openImageModal(imageSrc, caption, coords) {
    let modal = document.getElementById('image-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'image-modal';
        modal.className = 'image-modal';
        modal.innerHTML = `
            <div class="modal-content">
                <span class="modal-close" onclick="closeImageModal()">&times;</span>
                <img id="modal-image" src="" alt="Extracted Image">
                <div class="modal-info">
                    <p id="modal-caption"></p>
                    <p id="modal-coords"></p>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    document.getElementById('modal-image').src = imageSrc;
    ui.setText('modal-caption', caption);
    ui.setText('modal-coords', coords);
    modal.classList.add('active');
}

function closeImageModal() {
    const modal = document.getElementById('image-modal');
    if (modal) modal.classList.remove('active');
}

// Environment Check
async function checkEnvironment() {
    const envDiv = document.getElementById('environment-check');
    const envDetails = document.getElementById('env-details');

    ui.show('environment-check');
    ui.setHtml('env-details', '<div class="loader"></div> Checking environment...');

    try {
        const data = await api.get('/check-environment');

        let html = '<ul>';
        html += `<li>Working directory: <code>${data.cwd}</code></li>`;
        html += `<li>Python version: <code>${data.python_version}</code></li>`;

        if (data.missing_scripts.length === 0) {
            html += '<li class="env-success">✓ All required scripts found</li>';
        } else {
            html += `<li class="env-error">✗ Missing scripts: <code>${data.missing_scripts.join(', ')}</code></li>`;
        }

        if (data.pdf_files.length > 0) {
            html += `<li class="env-success">✓ Found ${data.pdf_files.length} PDF files</li>`;
        } else {
            html += '<li class="env-error">✗ No PDF files found in the working directory</li>';
        }

        html += '</ul>';
        ui.setHtml('env-details', html);
    } catch (error) {
        ui.setHtml('env-details', `<div class="env-error">Error checking environment: ${error.message}</div>`);
    }
}

// Manual Command Execution
async function manuallyRunScript() {
    const command = prompt("Enter command to run:");
    if (!command) return;

    const outputDiv = document.getElementById('output');
    ui.setText('output', 'Running command: ' + command + '\nPlease wait...');
    ui.show('output');

    const formData = new FormData();
    formData.append('command', command);

    try {
        const data = await api.post('/run-manual-command', formData);
        ui.setText('output',
            'Command: ' + command + '\n\n' +
            (data.success ? 'Success!\n\n' : 'Failed!\n\n') +
            (data.output || '') +
            (data.error ? '\n\nError: ' + data.error : '')
        );
    } catch (error) {
        ui.setText('output', 'Error running command: ' + error.message);
    }
}

// Initialize Application
window.addEventListener('DOMContentLoaded', async function() {
    // Load PDF files
    const pdfStatus = document.getElementById('pdf-load-status');
    ui.setHtml('pdf-load-status', '<div class="loader"></div> Loading PDF files...');

    try {
        const data = await api.get('/pdf-files');
        const select = document.getElementById('pdf_file');

        if (data.length === 0) {
            ui.setHtml('pdf-load-status', '<span class="error">No PDF files found</span>');
            return;
        }

        data.forEach(file => {
            const option = document.createElement('option');
            option.value = file;
            option.textContent = file;
            select.appendChild(option);
        });

        ui.setHtml('pdf-load-status', `<span class="success">Loaded ${data.length} PDF files</span>`);
    } catch (error) {
        ui.setHtml('pdf-load-status', '<span class="error">Error: ' + error.message + '</span>');
    }

    // Add event listeners
    document.getElementById('pdf_file').addEventListener('change', loadPDFPreview);
    document.getElementById('page_num').addEventListener('change', loadPDFPreview);

    const previewPageInput = document.getElementById('preview-page-input');
    if (previewPageInput) {
        previewPageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') goToPreviewPage();
        });
    }

    // Initial checks
    checkEnvironment();
    loadExtractedImages();

    // Check for existing visualization
    try {
        const response = await fetch('/results/visualization_page_1.png');
        if (response.ok) {
            appState.generatedOutputs.visualizer = '/results/visualization_page_1.png';
        }
    } catch {}
});