// Keep track of active tasks
const activeTasks = {};
let pollingInterval = null;

// Keep track of generated outputs
const generatedOutputs = {
    visualizer: null,
    extractor: false
};

// Load and display PDF preview
function loadPDFPreview() {
    const pdfFile = document.getElementById('pdf_file').value;
    const pageNum = document.getElementById('page_num').value;

    if (!pdfFile) {
        document.getElementById('pdf-preview-container').classList.add('hidden');
        return;
    }

    // Update page number display
    document.getElementById('preview-page-num').textContent = pageNum;

    // Load the preview image
    const previewImg = document.getElementById('pdf-preview-image');
    previewImg.src = `/pdf-preview/${encodeURIComponent(pdfFile)}/${pageNum}`;

    // Show the preview container
    document.getElementById('pdf-preview-container').classList.remove('hidden');

    // Handle loading errors
    previewImg.onerror = function() {
        this.alt = 'Failed to load PDF preview';
        console.error('Failed to load PDF preview');
    };
}

// Toggle batch mode UI
function toggleBatchMode() {
    const batchMode = document.getElementById('batch_mode').checked;
    const batchSettings = document.getElementById('batch-settings');
    const batchBtn = document.getElementById('batch-btn');
    const analyzerBtn = document.getElementById('analyzer-btn');
    const pageNumInput = document.getElementById('page_num');

    if (batchMode) {
        batchSettings.classList.remove('hidden');
        batchBtn.classList.remove('hidden');
        analyzerBtn.textContent = 'Analyze Single Page';
        pageNumInput.disabled = true;

        // Update preview to show start page
        const startPage = document.getElementById('batch_start').value;
        document.getElementById('page_num').value = startPage;
        loadPDFPreview();
    } else {
        batchSettings.classList.add('hidden');
        batchBtn.classList.add('hidden');
        analyzerBtn.textContent = 'Start Analysis';
        pageNumInput.disabled = false;
    }
}

// Update batch start page preview
function updateBatchPreview() {
    if (document.getElementById('batch_mode').checked) {
        const startPage = document.getElementById('batch_start').value;
        document.getElementById('page_num').value = startPage;
        loadPDFPreview();
    }
}

// Run batch processing
function runBatchProcessing() {
    const pdfFile = document.getElementById('pdf_file').value;
    const adjust = document.getElementById('adjust').checked;
    const batchStart = document.getElementById('batch_start').value;
    const batchEnd = document.getElementById('batch_end').value;
    const batchPages = document.getElementById('batch_pages').value;

    if (!pdfFile) {
        alert('Please select a PDF file');
        return;
    }

    // Disable buttons
    document.getElementById('batch-btn').disabled = true;
    document.getElementById('analyzer-btn').disabled = true;

    // Show batch status
    const batchStatus = document.getElementById('batch-status');
    batchStatus.innerHTML = `
        <h4>Batch Processing Progress</h4>
        <div class="batch-progress">
            <div class="batch-progress-bar">
                <div class="batch-progress-fill" style="width: 0%"></div>
                <div class="batch-progress-text">0%</div>
            </div>
        </div>
        <div class="batch-details" id="batch-details">
            <div class="batch-page-status processing">Starting batch processing...</div>
        </div>
    `;
    batchStatus.classList.remove('hidden');

    // Create form data
    const formData = new FormData();
    formData.append('pdf_file', pdfFile);
    formData.append('adjust', adjust);
    formData.append('batch_start', batchStart);
    formData.append('batch_end', batchEnd || '');
    formData.append('batch_pages', batchPages || '');

    // Send request
    fetch('/run-batch', {
        method: 'POST',
        body: formData
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to start batch processing');
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.task_id) {
                // Store task information
                activeTasks[data.task_id] = {
                    type: 'batch',
                    totalPages: data.total_pages
                };

                // Start polling for updates
                startPolling();

                // Update batch details
                document.getElementById('batch-details').innerHTML =
                    `<div class="batch-page-status processing">Processing ${data.total_pages} pages...</div>`;
            } else {
                // Failed to start task
                batchStatus.innerHTML = `<span class="error">✗ Failed to start batch processing: ${data.error || 'Unknown error'}</span>`;
                document.getElementById('batch-btn').disabled = false;
                document.getElementById('analyzer-btn').disabled = false;
            }
        })
        .catch(error => {
            console.error('Error starting batch processing:', error);
            batchStatus.innerHTML = `<span class="error">✗ Error: ${error.message}</span>`;
            document.getElementById('batch-btn').disabled = false;
            document.getElementById('analyzer-btn').disabled = false;
        });
}

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

    // Show previously generated content when switching tabs
    if (tabName === 'analyzer') {
        // Load PDF preview if a PDF is selected
        loadPDFPreview();
    } else if (tabName === 'visualizer' && generatedOutputs.visualizer) {
        document.getElementById('result-image').src = generatedOutputs.visualizer + '?t=' + new Date().getTime();
        document.getElementById('image-container').classList.remove('hidden');
    } else if (tabName === 'extractor' && generatedOutputs.extractor) {
        loadExtractedImages();
    }
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

// Load extracted images from the results folder
function loadExtractedImages() {
    const imageGallery = document.getElementById('extracted-images-gallery');
    const imageContainer = document.getElementById('extracted-images-container');

    // First try to load the index.html to get the list of images
    fetch('/results/pictures/index.html')
        .then(response => {
            if (!response.ok) {
                throw new Error('No extracted images found');
            }
            return response.text();
        })
        .then(html => {
            // Parse the HTML to extract image information
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
            imageContainer.classList.remove('hidden');
            generatedOutputs.extractor = true;
        })
        .catch(error => {
            console.log('No extracted images found:', error);
            imageGallery.innerHTML = '<div class="no-images">No images have been extracted yet. Run the image extraction first.</div>';
            generatedOutputs.extractor = false;
        });
}

// Open image in modal for better viewing
function openImageModal(imageSrc, caption, coords) {
    // Create modal if it doesn't exist
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

    // Set image and info
    document.getElementById('modal-image').src = imageSrc;
    document.getElementById('modal-caption').textContent = caption;
    document.getElementById('modal-coords').textContent = coords;

    // Show modal
    modal.classList.add('active');
}

// Close image modal
function closeImageModal() {
    const modal = document.getElementById('image-modal');
    if (modal) {
        modal.classList.remove('active');
    }
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
                if (taskInfo.type === 'batch') {
                    // Handle batch processing updates
                    updateBatchStatus(taskId, data, taskInfo);
                } else {
                    // Handle single page processing (existing code)
                    updateSinglePageStatus(taskId, data, taskInfo);
                }
            })
            .catch(error => {
                console.error('Error checking task status:', error);
            });
    }
}

// New function to update batch processing status
function updateBatchStatus(taskId, data, taskInfo) {
    const batchStatus = document.getElementById('batch-status');
    const batchDetails = document.getElementById('batch-details');

    if (data.done) {
        if (data.success) {
            // Update progress to 100%
            const progressBar = batchStatus.querySelector('.batch-progress-fill');
            const progressText = batchStatus.querySelector('.batch-progress-text');
            if (progressBar) {
                progressBar.style.width = '100%';
                progressText.textContent = '100%';
            }

            // Show completion message with link to report
            let detailsHTML = '<div class="batch-page-status success">✓ Batch processing completed!</div>';

            if (data.report_file) {
                detailsHTML += `<div class="batch-page-status"><a href="${data.report_file}" target="_blank" class="batch-report-link">View Batch Report</a></div>`;
            }

            if (data.summary) {
                detailsHTML += `<div class="batch-page-status">${data.summary}</div>`;
            }

            batchDetails.innerHTML = detailsHTML;

            // Enable buttons
            document.getElementById('batch-btn').disabled = false;
            document.getElementById('analyzer-btn').disabled = false;

            // Update progress indicator
            updateProgress(3);

            // Remove from active tasks
            delete activeTasks[taskId];
            checkAndStopPolling();
        } else {
            // Task failed
            batchDetails.innerHTML = `<div class="batch-page-status error">✗ Failed: ${data.error || 'Unknown error'}</div>`;

            // Enable buttons
            document.getElementById('batch-btn').disabled = false;
            document.getElementById('analyzer-btn').disabled = false;

            // Remove from active tasks
            delete activeTasks[taskId];
            checkAndStopPolling();
        }
    } else {
        // Still running - update progress
        if (data.progress) {
            const progressBar = batchStatus.querySelector('.batch-progress-fill');
            const progressText = batchStatus.querySelector('.batch-progress-text');
            if (progressBar) {
                const percentage = Math.round((data.progress.completed / data.progress.total) * 100);
                progressBar.style.width = percentage + '%';
                progressText.textContent = percentage + '%';
            }

            // Update details with current status
            let detailsHTML = `<div class="batch-page-status processing">Processing page ${data.progress.current_page} of ${data.progress.total}...</div>`;

            if (data.progress.completed_pages && data.progress.completed_pages.length > 0) {
                detailsHTML += '<div class="batch-page-status">Completed pages: ' +
                    data.progress.completed_pages.join(', ') + '</div>';
            }

            batchDetails.innerHTML = detailsHTML;
        }
    }
}

// Rename the existing status update function
function updateSinglePageStatus(taskId, data, taskInfo) {
    // This is the existing code for handling single page processing
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
                generatedOutputs.visualizer = '/' + data.image_file;
                document.getElementById('result-image').src = generatedOutputs.visualizer + '?t=' + new Date().getTime();
                document.getElementById('image-container').classList.remove('hidden');
            }

            // Load extracted images if extractor completed
            if (taskInfo.type === 'extractor') {
                setTimeout(() => {
                    loadExtractedImages();
                }, 1000); // Small delay to ensure files are written
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

    // Don't hide content when switching between tabs
    // Only hide when running a new analysis on the same tab
    if (script === 'analyzer') {
        // Reset everything when running analyzer
        document.getElementById('image-container').classList.add('hidden');
        document.getElementById('extracted-images-container').classList.add('hidden');
        generatedOutputs.visualizer = null;
        generatedOutputs.extractor = false;
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

    // Add event listeners for PDF selection and page number changes
    document.getElementById('pdf_file').addEventListener('change', loadPDFPreview);
    document.getElementById('page_num').addEventListener('change', loadPDFPreview);

    // Add batch mode event listeners
    document.getElementById('batch_start').addEventListener('change', updateBatchPreview);
    document.getElementById('batch_pages').addEventListener('input', function() {
        // Clear end page when specific pages are entered
        if (this.value) {
            document.getElementById('batch_end').value = '';
        }
    });
    document.getElementById('batch_end').addEventListener('input', function() {
        // Clear specific pages when end page is entered
        if (this.value) {
            document.getElementById('batch_pages').value = '';
        }
    });

    // Run an environment check on startup
    checkEnvironment();

    // Try to load any existing extracted images
    loadExtractedImages();

    // Check if there's an existing visualization
    fetch('/results/visualization_page_1.png')
        .then(response => {
            if (response.ok) {
                generatedOutputs.visualizer = '/results/visualization_page_1.png';
            }
        })
        .catch(() => {
            // No existing visualization
        });
});