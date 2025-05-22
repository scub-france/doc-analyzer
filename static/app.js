// Keep track of active tasks
const activeTasks = {};
let pollingInterval = null;

// PDF preview variables
let currentPdf = null;
let currentPageNum = 1;
let totalPages = 0;
let renderScale = 1.0;

// Initialize PDF.js
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

// Tab switching functionality
function switchTab(tabName) {
    // Hide all tab contents
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(content => content.classList.remove('active'));

    // Remove active class from all tab buttons
    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => button.classList.remove('active'));

    // Show selected tab content
    document.getElementById(tabName + '-tab').classList.add('active');

    // Add active class to selected tab button
    event.target.classList.add('active');
}

// Update progress indicator
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

// PDF Preview Functions
async function loadPdfPreview(pdfFile) {
    if (!pdfFile) {
        hidePdfPreview();
        return;
    }

    const previewContainer = document.getElementById('pdf-preview-container');
    const loadingDiv = document.getElementById('pdf-preview-loading');
    const canvas = document.getElementById('pdf-preview-canvas');

    // Show preview container and loading
    previewContainer.classList.remove('hidden');
    loadingDiv.classList.remove('hidden');
    canvas.classList.add('hidden');

    try {
        // Load the PDF
        const loadingTask = pdfjsLib.getDocument(`/${pdfFile}`);
        currentPdf = await loadingTask.promise;
        totalPages = currentPdf.numPages;

        // Update page info
        updatePageInfo();
        updatePageControls();

        // Render the current page
        await renderPage();

        // Hide loading, show canvas
        loadingDiv.classList.add('hidden');
        canvas.classList.remove('hidden');

    } catch (error) {
        console.error('Error loading PDF preview:', error);
        loadingDiv.innerHTML = '<span class="error">Error loading PDF preview: ' + error.message + '</span>';
    }
}

async function renderPage() {
    if (!currentPdf) return;

    const canvas = document.getElementById('pdf-preview-canvas');
    const ctx = canvas.getContext('2d');

    try {
        // Get the page
        const page = await currentPdf.getPage(currentPageNum);

        // Calculate scale to fit container width (max 600px)
        const viewport = page.getViewport({ scale: 1.0 });
        const maxWidth = 600;
        renderScale = Math.min(maxWidth / viewport.width, 1.5);

        const scaledViewport = page.getViewport({ scale: renderScale });

        // Set canvas dimensions
        canvas.height = scaledViewport.height;
        canvas.width = scaledViewport.width;

        // Render the page
        const renderContext = {
            canvasContext: ctx,
            viewport: scaledViewport
        };

        await page.render(renderContext).promise;

        // Update zoom info
        document.getElementById('zoom-info').textContent = Math.round(renderScale * 100) + '%';

    } catch (error) {
        console.error('Error rendering page:', error);
    }
}

function updatePageInfo() {
    document.getElementById('page-info').textContent = `Page ${currentPageNum} of ${totalPages}`;
}

function updatePageControls() {
    document.getElementById('prev-page-btn').disabled = currentPageNum <= 1;
    document.getElementById('next-page-btn').disabled = currentPageNum >= totalPages;
}

async function changePage(delta) {
    const newPage = currentPageNum + delta;
    if (newPage >= 1 && newPage <= totalPages) {
        currentPageNum = newPage;

        // Update the page number input
        document.getElementById('page_num').value = currentPageNum;

        updatePageInfo();
        updatePageControls();
        await renderPage();
    }
}

async function refreshPreview() {
    const pdfFile = document.getElementById('pdf_file').value;
    if (pdfFile) {
        await loadPdfPreview(pdfFile);
    }
}

function hidePdfPreview() {
    document.getElementById('pdf-preview-container').classList.add('hidden');
    currentPdf = null;
    totalPages = 0;
    currentPageNum = 1;
}

// Event listeners for PDF selection and page changes
document.addEventListener('DOMContentLoaded', function() {
    // PDF file selection change
    document.getElementById('pdf_file').addEventListener('change', async function() {
        const selectedFile = this.value;
        if (selectedFile) {
            await loadPdfPreview(selectedFile);
        } else {
            hidePdfPreview();
        }
    });

    // Page number input change
    document.getElementById('page_num').addEventListener('change', async function() {
        const pageNum = parseInt(this.value);
        if (pageNum >= 1 && pageNum <= totalPages && pageNum !== currentPageNum) {
            currentPageNum = pageNum;
            updatePageInfo();
            updatePageControls();
            await renderPage();
        }
    });
});

// Load PDF files on page load
window.addEventListener('DOMContentLoaded', function() {
    const pdfStatus = document.getElementById('pdf-load-status');
    pdfStatus.innerHTML = '<div class="loader"></div> Loading PDF files...';

    fetch('/pdf-files')
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to load PDF files');
            }
            return response.json();
        })
        .then(data => {
            const select = document.getElementById('pdf_file');
            if (data.length === 0) {
                pdfStatus.innerHTML = '<span class="error">No PDF files found in the current directory</span>';
                return;
            }

            data.forEach(file => {
                const option = document.createElement('option');
                option.value = file;
                option.textContent = file;
                select.appendChild(option);
            });
            pdfStatus.innerHTML = '<span class="success">Loaded ' + data.length + ' PDF files</span>';
        })
        .catch(error => {
            console.error('Error loading PDFs:', error);
            pdfStatus.innerHTML = '<span class="error">Error: ' + error.message + '</span>';
        });

    // Run an environment check on startup
    checkEnvironment();
});

// Check the environment
function checkEnvironment() {
    const envDiv = document.getElementById('environment-check');
    const envDetails = document.getElementById('env-details');

    envDiv.classList.remove('hidden');
    envDetails.innerHTML = '<div class="loader"></div> Checking environment...';

    fetch('/check-environment')
        .then(response => response.json())
        .then(data => {
            let html = '<ul>';

            // Current working directory
            html += '<li>Working directory: <code>' + data.cwd + '</code></li>';

            // Python version
            html += '<li>Python version: <code>' + data.python_version + '</code></li>';

            // Required scripts check
            if (data.missing_scripts.length === 0) {
                html += '<li class="env-success">✓ All required scripts found</li>';
            } else {
                html += '<li class="env-error">✗ Missing scripts: <code>' + data.missing_scripts.join(', ') + '</code></li>';
            }

            // PDF files check
            if (data.pdf_files.length > 0) {
                html += '<li class="env-success">✓ Found ' + data.pdf_files.length + ' PDF files: <code>' + data.pdf_files.join(', ') + '</code></li>';
            } else {
                html += '<li class="env-error">✗ No PDF files found in the working directory</li>';
            }

            // Results directory check
            if (data.results_dir_exists) {
                html += '<li class="env-success">✓ Results directory exists</li>';
                if (data.results_dir_writable) {
                    html += '<li class="env-success">✓ Results directory is writable</li>';
                } else {
                    html += '<li class="env-error">✗ Results directory is not writable</li>';
                }
            } else {
                html += '<li class="env-error">✗ Results directory does not exist</li>';
            }

            html += '</ul>';

            // List of all files for debugging
            html += '<details><summary>All files in directory (' + data.files.length + ' files)</summary><pre>' +
                data.files.join('\n') + '</pre></details>';

            envDetails.innerHTML = html;
        })
        .catch(error => {
            envDetails.innerHTML = '<div class="env-error">Error checking environment: ' + error.message + '</div>';
        });
}

// Manual command execution for debugging
function manuallyRunScript() {
    const command = prompt("Enter command to run (e.g., 'python analyzer.py --image document.pdf --page 1')");
    if (!command) return;

    const outputDiv = document.getElementById('output');
    outputDiv.textContent = 'Running command: ' + command + '\nPlease wait...';
    outputDiv.classList.remove('hidden');

    // Create form data
    const formData = new FormData();
    formData.append('command', command);

    // Send the command directly to backend
    fetch('/run-manual-command', {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            outputDiv.textContent = 'Command: ' + command + '\n\n' +
                (data.success ? 'Success!\n\n' : 'Failed!\n\n') +
                (data.output || '') +
                (data.error ? '\n\nError: ' + data.error : '');
        })
        .catch(error => {
            outputDiv.textContent = 'Error running command: ' + error.message;
        });
}

// Start polling for task updates
function startPolling() {
    if (pollingInterval) {
        return; // Already polling
    }

    pollingInterval = setInterval(pollTasks, 1000);
}

// Stop polling when no active tasks
function checkAndStopPolling() {
    if (Object.keys(activeTasks).length === 0 && pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

// Poll for task updates
function pollTasks() {
    for (const taskId in activeTasks) {
        const taskInfo = activeTasks[taskId];

        fetch(`/task-status/${taskId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to check task status');
                }
                return response.json();
            })
            .then(data => {
                // Update status display
                const statusElement = document.getElementById(`${taskInfo.type}-status`);

                if (data.done) {
                    if (data.success) {
                        // Task completed successfully
                        statusElement.innerHTML = '<span class="success">✓ Completed successfully!</span>';
                        statusElement.classList.remove('hidden');

                        // Enable button
                        document.getElementById(`${taskInfo.type}-btn`).disabled = false;

                        // Display output
                        const outputDiv = document.getElementById('output');
                        outputDiv.textContent = data.output;
                        outputDiv.classList.remove('hidden');

                        // Show image if available for visualizer
                        if (taskInfo.type === 'visualizer' && data.image_file) {
                            document.getElementById('result-image').src = '/' + data.image_file + '?t=' + new Date().getTime();
                            document.getElementById('image-container').classList.remove('hidden');
                        }

                        // Enable next step button and update progress
                        if (taskInfo.type === 'analyzer') {
                            document.getElementById('visualizer-btn').disabled = false;
                            updateProgress(1);
                        } else if (taskInfo.type === 'visualizer') {
                            document.getElementById('extractor-btn').disabled = false;
                            updateProgress(2);
                        } else if (taskInfo.type === 'extractor') {
                            updateProgress(3);
                        }

                        // Remove from active tasks
                        delete activeTasks[taskId];
                        checkAndStopPolling();
                    } else {
                        // Task failed
                        statusElement.innerHTML = '<span class="error">✗ Failed: ' + (data.error || 'Unknown error') + '</span>';
                        statusElement.classList.remove('hidden');
                        document.getElementById(`${taskInfo.type}-btn`).disabled = false;

                        // Display error output
                        const outputDiv = document.getElementById('output');
                        outputDiv.textContent = 'Error: ' + (data.error || 'Unknown error');
                        outputDiv.classList.remove('hidden');

                        // Remove from active tasks
                        delete activeTasks[taskId];
                        checkAndStopPolling();
                    }
                } else {
                    // Still running
                    statusElement.innerHTML = '<div class="loader"></div><span class="working">Running...</span>';
                    statusElement.classList.remove('hidden');
                }
            })
            .catch(error => {
                console.error('Error checking task status:', error);
            });
    }
}

function runScript(script) {
    const pdfFile = document.getElementById('pdf_file').value;
    const pageNum = document.getElementById('page_num').value;
    const adjust = document.getElementById('adjust').checked;

    if (!pdfFile) {
        alert('Please select a PDF file');
        return;
    }

    // Disable button
    const button = document.getElementById(`${script}-btn`);
    button.disabled = true;

    // Create form data
    const formData = new FormData();
    formData.append('pdf_file', pdfFile);
    formData.append('page_num', pageNum);
    formData.append('adjust', adjust);

    // Show running status
    const statusElement = document.getElementById(`${script}-status`);
    statusElement.innerHTML = '<div class="loader"></div><span class="working">Starting...</span>';
    statusElement.classList.remove('hidden');

    // Clear previous output
    document.getElementById('output').classList.add('hidden');

    // Hide previous image if not running visualizer
    if (script !== 'visualizer') {
        document.getElementById('image-container').classList.add('hidden');
    }

    // Determine endpoint
    let endpoint;
    switch(script) {
        case 'analyzer':
            endpoint = '/run-analyzer';
            // Disable next step buttons
            document.getElementById('visualizer-btn').disabled = true;
            document.getElementById('extractor-btn').disabled = true;
            updateProgress(0);
            break;
        case 'visualizer':
            endpoint = '/run-visualizer';
            // Disable next step button
            document.getElementById('extractor-btn').disabled = true;
            break;
        case 'extractor':
            endpoint = '/run-extractor';
            break;
    }

    // Send request
    fetch(endpoint, {
        method: 'POST',
        body: formData
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to start task');
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.task_id) {
                // Store task information
                activeTasks[data.task_id] = {
                    type: script,
                    pageNum: pageNum
                };

                // Start polling for updates
                startPolling();

                // Update status
                statusElement.innerHTML = '<div class="loader"></div><span class="working">Running...</span>';

                // Show initial output
                const outputDiv = document.getElementById('output');
                outputDiv.textContent = data.message || 'Task started, please wait...';
                outputDiv.classList.remove('hidden');
            } else {
                // Failed to start task
                statusElement.innerHTML = '<span class="error">✗ Failed to start task</span>';
                button.disabled = false;

                // Show error
                const outputDiv = document.getElementById('output');
                outputDiv.textContent = 'Error: ' + (data.error || 'Failed to start task');
                outputDiv.classList.remove('hidden');
            }
        })
        .catch(error => {
            console.error('Error starting task:', error);
            statusElement.innerHTML = '<span class="error">✗ ' + error.message + '</span>';
            button.disabled = false;

            // Show error
            const outputDiv = document.getElementById('output');
            outputDiv.textContent = 'Error: ' + error.message;
            outputDiv.classList.remove('hidden');
        });
}