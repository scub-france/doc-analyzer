// Keep track of active tasks
const activeTasks = {};
let pollingInterval = null;

// Helper functions for UI
const UI = {
    showLoader: (elementId) => {
        const el = document.getElementById(elementId);
        el.innerHTML = '<div class="loader"></div><span class="working">Processing...</span>';
    },
    showSuccess: (elementId, message = 'Completed') => {
        const el = document.getElementById(elementId);
        el.innerHTML = `<span class="success">✓ ${message}</span>`;
    },
    showError: (elementId, message = 'Failed') => {
        const el = document.getElementById(elementId);
        el.innerHTML = `<span class="error">✗ ${message}</span>`;
    },
    showOutput: (content) => {
        const outputDiv = document.getElementById('output');
        outputDiv.textContent = content;
        outputDiv.classList.remove('hidden');
        // Scroll to show output
        outputDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },
    showImage: (src) => {
        const img = document.getElementById('result-image');
        const container = document.getElementById('image-container');
        img.src = src;
        container.classList.remove('hidden');
        // Scroll to show image
        container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },
    enableButton: (buttonId) => {
        document.getElementById(buttonId).disabled = false;
    },
    disableButton: (buttonId) => {
        document.getElementById(buttonId).disabled = true;
    }
};

// Load PDF files on page load
window.addEventListener('DOMContentLoaded', function() {
    const pdfStatus = document.getElementById('pdf-load-status');
    pdfStatus.innerHTML = '<div class="loader"></div><span class="working">Loading PDF files...</span>';

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
                UI.showError('pdf-load-status', 'No PDF files found in the current directory');
                return;
            }

            data.forEach(file => {
                const option = document.createElement('option');
                option.value = file;
                option.textContent = file;
                select.appendChild(option);
            });
            UI.showSuccess('pdf-load-status', `Loaded ${data.length} PDF files`);
        })
        .catch(error => {
            console.error('Error loading PDFs:', error);
            UI.showError('pdf-load-status', `Error: ${error.message}`);
        });

    // Run an environment check on startup
    checkEnvironment();
});

// Check the environment
function checkEnvironment() {
    const envDiv = document.getElementById('environment-check');
    const envDetails = document.getElementById('env-details');

    envDiv.classList.remove('hidden');
    envDetails.innerHTML = '<div class="loader"></div><span class="working">Checking environment...</span>';

    fetch('/check-environment')
        .then(response => response.json())
        .then(data => {
            let html = '<div class="mt-2">';

            // Current working directory
            html += `<p><strong>Working directory:</strong> <code>${data.cwd}</code></p>`;

            // Python version
            html += `<p><strong>Python version:</strong> <code>${data.python_version}</code></p>`;

            // Required scripts check
            if (data.missing_scripts.length === 0) {
                html += '<p class="env-success">All required scripts found</p>';
            } else {
                html += `<p class="env-error">Missing scripts: <code>${data.missing_scripts.join(', ')}</code></p>`;
            }

            // PDF files check
            if (data.pdf_files.length > 0) {
                html += `<p class="env-success">Found ${data.pdf_files.length} PDF files</p>`;
                html += '<details class="mt-1"><summary>PDF Files</summary><ul>';
                data.pdf_files.forEach(file => {
                    html += `<li><code>${file}</code></li>`;
                });
                html += '</ul></details>';
            } else {
                html += '<p class="env-error">No PDF files found in the working directory</p>';
            }

            // Results directory check
            if (data.results_dir_exists) {
                html += '<p class="env-success">Results directory exists</p>';
                if (data.results_dir_writable) {
                    html += '<p class="env-success">Results directory is writable</p>';
                } else {
                    html += '<p class="env-error">Results directory is not writable</p>';
                }
            } else {
                html += '<p class="env-error">Results directory does not exist</p>';
            }

            html += '</div>';

            // List of all files for debugging (collapsible)
            html += `<details class="mt-2"><summary>All files in directory (${data.files.length} files)</summary><pre>${data.files.join('\n')}</pre></details>`;

            envDetails.innerHTML = html;
        })
        .catch(error => {
            envDetails.innerHTML = `<div class="env-error mt-2">Error checking environment: ${error.message}</div>`;
        });
}

// Manual command execution for debugging
function manuallyRunScript() {
    const command = prompt("Enter command to run (e.g., 'python analyzer.py --image document.pdf --page 1')");
    if (!command) return;

    UI.showOutput(`Running command: ${command}\nPlease wait...`);

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
            UI.showOutput(
                `Command: ${command}\n\n${data.success ? 'Success!\n\n' : 'Failed!\n\n'}${data.output || ''}${data.error ? '\n\nError: ' + data.error : ''}`
            );
        })
        .catch(error => {
            UI.showOutput(`Error running command: ${error.message}`);
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
                        UI.showSuccess(`${taskInfo.type}-status`, 'Completed');

                        // Enable button
                        UI.enableButton(`${taskInfo.type}-btn`);

                        // Display output
                        UI.showOutput(data.output);

                        // Show image if available for visualizer
                        if (taskInfo.type === 'visualizer' && data.image_file) {
                            UI.showImage(`/${data.image_file}?t=${new Date().getTime()}`);
                        }

                        // Enable next step button if applicable
                        if (taskInfo.type === 'analyzer') {
                            UI.enableButton('visualizer-btn');
                        } else if (taskInfo.type === 'visualizer') {
                            UI.enableButton('extractor-btn');
                        }

                        // Remove from active tasks
                        delete activeTasks[taskId];
                        checkAndStopPolling();
                    } else {
                        // Task failed
                        UI.showError(`${taskInfo.type}-status`, data.error || 'Unknown error');
                        UI.enableButton(`${taskInfo.type}-btn`);

                        // Display error output
                        UI.showOutput(`Error: ${data.error || 'Unknown error'}`);

                        // Remove from active tasks
                        delete activeTasks[taskId];
                        checkAndStopPolling();
                    }
                } else {
                    // Still running
                    statusElement.innerHTML = '<div class="loader"></div><span class="working">Processing...</span>';
                }
            })
            .catch(error => {
                console.error('Error checking task status:', error);
                UI.showError(`${taskInfo.type}-status`, 'Failed to check status');
                UI.enableButton(`${taskInfo.type}-btn`);

                // Remove from active tasks to prevent endless error messages
                delete activeTasks[taskId];
                checkAndStopPolling();
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
    UI.disableButton(`${script}-btn`);

    // Create form data
    const formData = new FormData();
    formData.append('pdf_file', pdfFile);
    formData.append('page_num', pageNum);
    formData.append('adjust', adjust);

    // Show running status
    UI.showLoader(`${script}-status`);

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
            UI.disableButton('visualizer-btn');
            UI.disableButton('extractor-btn');
            break;
        case 'visualizer':
            endpoint = '/run-visualizer';
            // Disable next step button
            UI.disableButton('extractor-btn');
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
                UI.showLoader(`${script}-status`);

                // Show initial output
                UI.showOutput(data.message || 'Task started, please wait...');
            } else {
                // Failed to start task
                UI.showError(`${script}-status`, 'Failed to start task');
                UI.enableButton(`${script}-btn`);

                // Show error
                UI.showOutput(`Error: ${data.error || 'Failed to start task'}`);
            }
        })
        .catch(error => {
            console.error('Error starting task:', error);
            UI.showError(`${script}-status`, error.message);
            UI.enableButton(`${script}-btn`);

            // Show error
            UI.showOutput(`Error: ${error.message}`);
        });
}