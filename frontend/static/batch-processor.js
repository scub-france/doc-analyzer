// Batch Processor State Management
const batchState = {
    isProcessing: false,
    isPaused: false,
    currentBatchId: null,
    totalPages: 0,
    processedPages: 0,
    startTime: null,
    pageStatuses: {},
    results: {
        successful: 0,
        failed: 0,
        totalImages: 0,
        failedPages: []
    },
    autoScroll: true
};

// Timer for elapsed time
let elapsedTimer = null;

// Initialize on page load
window.addEventListener('DOMContentLoaded', function() {
    loadPDFFiles();
    setupEventListeners();
    checkBatchEnvironment();
});

// Load available PDF files
function loadPDFFiles() {
    fetch('/pdf-files')
        .then(response => response.json())
        .then(data => {
            const select = document.getElementById('batch_pdf_file');
            data.forEach(file => {
                const option = document.createElement('option');
                option.value = file;
                option.textContent = file;
                select.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error loading PDFs:', error);
            addConsoleMessage('Error loading PDF files: ' + error.message, 'error');
        });
}

// Setup event listeners
function setupEventListeners() {
    // PDF selection change
    document.getElementById('batch_pdf_file').addEventListener('change', function() {
        if (this.value) {
            fetchPDFInfo(this.value);
        } else {
            document.getElementById('batch-pdf-info').classList.add('hidden');
        }
    });

    // Page range radio buttons
    document.querySelectorAll('input[name="page_range"]').forEach(radio => {
        radio.addEventListener('change', function() {
            const customRange = document.getElementById('custom-range');
            if (this.value === 'range') {
                customRange.classList.remove('hidden');
            } else {
                customRange.classList.add('hidden');
            }
        });
    });
}

// Fetch PDF information (page count)
function fetchPDFInfo(pdfFile) {
    fetch(`/pdf-info/${encodeURIComponent(pdfFile)}`)
        .then(response => response.json())
        .then(data => {
            document.getElementById('total-pages').textContent = data.pageCount;
            document.getElementById('batch-pdf-info').classList.remove('hidden');

            // Update max values for custom range
            document.getElementById('start_page').max = data.pageCount;
            document.getElementById('end_page').max = data.pageCount;
            document.getElementById('end_page').value = data.pageCount;
        })
        .catch(error => {
            console.error('Error fetching PDF info:', error);
            addConsoleMessage('Error fetching PDF info: ' + error.message, 'error');
        });
}

// Start batch processing
function startBatchProcessing() {
    const pdfFile = document.getElementById('batch_pdf_file').value;
    if (!pdfFile) {
        alert('Please select a PDF file');
        return;
    }

    // Get page range
    const pageRangeType = document.querySelector('input[name="page_range"]:checked').value;
    let startPage = 1;
    let endPage = parseInt(document.getElementById('total-pages').textContent);

    if (pageRangeType === 'range') {
        startPage = parseInt(document.getElementById('start_page').value) || 1;
        endPage = parseInt(document.getElementById('end_page').value) || endPage;

        if (startPage > endPage) {
            alert('Invalid page range: start page must be less than or equal to end page');
            return;
        }
    }

    // Reset state
    resetBatchState();
    batchState.isProcessing = true;
    batchState.totalPages = endPage - startPage + 1;
    batchState.startTime = Date.now();

    // Update UI
    updateUIForProcessing(true);
    initializePageGrid(startPage, endPage);

    // Start elapsed timer
    startElapsedTimer();

    // Show console
    document.getElementById('console-output').classList.remove('hidden');
    addConsoleMessage(`Starting batch processing for ${pdfFile} (pages ${startPage}-${endPage})`, 'info');

    // Prepare request data
    const formData = new FormData();
    formData.append('pdf_file', pdfFile);
    formData.append('start_page', startPage);
    formData.append('end_page', endPage);
    formData.append('adjust', document.getElementById('batch_adjust').checked);
    formData.append('parallel', document.getElementById('parallel_processing').checked);
    formData.append('generate_report', document.getElementById('generate_report').checked);

    // Start batch processing
    fetch('/run-batch-processor', {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                batchState.currentBatchId = data.batch_id;
                addConsoleMessage(`Batch processing started with ID: ${data.batch_id}`, 'success');

                // Start polling for updates
                pollBatchStatus();
            } else {
                throw new Error(data.error || 'Failed to start batch processing');
            }
        })
        .catch(error => {
            console.error('Error starting batch processing:', error);
            addConsoleMessage('Error: ' + error.message, 'error');
            finishBatchProcessing(false);
        });
}

// Poll for batch status updates
function pollBatchStatus() {
    if (!batchState.isProcessing || !batchState.currentBatchId) {
        return;
    }

    fetch(`/batch-status/${batchState.currentBatchId}`)
        .then(response => response.json())
        .then(data => {
            updateBatchProgress(data);

            if (data.completed) {
                finishBatchProcessing(true);
            } else if (!batchState.isPaused) {
                // Continue polling
                setTimeout(pollBatchStatus, 1000);
            }
        })
        .catch(error => {
            console.error('Error polling batch status:', error);
            if (batchState.isProcessing) {
                setTimeout(pollBatchStatus, 2000); // Retry with longer delay
            }
        });
}

// Update batch progress
function updateBatchProgress(data) {
    // Update overall progress
    const percentage = Math.round((data.processed / data.total) * 100);
    document.getElementById('overall-percentage').textContent = percentage + '%';
    document.getElementById('overall-progress-fill').style.width = percentage + '%';
    document.getElementById('pages-completed').textContent = data.processed;
    document.getElementById('pages-total').textContent = data.total;

    // Update stage progress
    if (data.stages) {
        updateStageProgress('analysis', data.stages.analysis);
        updateStageProgress('visualization', data.stages.visualization);
        updateStageProgress('extraction', data.stages.extraction);
    }

    // Update page statuses
    if (data.page_statuses) {
        for (const [pageNum, status] of Object.entries(data.page_statuses)) {
            updatePageStatus(pageNum, status);
        }
    }

    // Update results
    if (data.results) {
        batchState.results = data.results;
        updateResultsSummary();
    }

    // Add log messages
    if (data.logs && data.logs.length > 0) {
        data.logs.forEach(log => {
            addConsoleMessage(log.message, log.level);
        });
    }

    // Update ETA
    if (data.eta) {
        document.getElementById('eta-time').textContent = formatTime(data.eta);
    }
}

// Update stage progress
function updateStageProgress(stage, data) {
    if (!data) return;

    const percentage = Math.round((data.completed / data.total) * 100);
    document.getElementById(`${stage}-percentage`).textContent = percentage + '%';
    document.getElementById(`${stage}-progress`).style.width = percentage + '%';
}

// Initialize page grid
function initializePageGrid(startPage, endPage) {
    const grid = document.getElementById('page-grid');
    grid.innerHTML = '';

    document.getElementById('batch-progress-panel').classList.remove('hidden');
    document.getElementById('page-status-grid').classList.remove('hidden');

    for (let i = startPage; i <= endPage; i++) {
        const pageItem = createPageStatusItem(i);
        grid.appendChild(pageItem);
        batchState.pageStatuses[i] = 'pending';
    }
}

// Create page status item
function createPageStatusItem(pageNum) {
    const item = document.createElement('div');
    item.className = 'page-status-item pending';
    item.id = `page-status-${pageNum}`;
    item.innerHTML = `
        <div class="page-number">Page ${pageNum}</div>
        <div class="page-status-icon">⏳</div>
        <div class="page-actions hidden">
            <button class="mini-btn" onclick="viewPageResults(${pageNum})" title="View results">
                👁️
            </button>
        </div>
    `;
    item.onclick = () => viewPageResults(pageNum);
    return item;
}

// Update page status
function updatePageStatus(pageNum, status) {
    const item = document.getElementById(`page-status-${pageNum}`);
    if (!item) return;

    // Remove all status classes
    item.classList.remove('pending', 'processing', 'completed', 'failed');

    // Add new status class
    item.classList.add(status.toLowerCase());

    // Update icon
    const icons = {
        'pending': '⏳',
        'processing': '🔄',
        'completed': '✅',
        'failed': '❌'
    };

    const iconElement = item.querySelector('.page-status-icon');
    iconElement.textContent = icons[status.toLowerCase()] || '❓';

    // Show actions for completed pages
    if (status.toLowerCase() === 'completed') {
        item.querySelector('.page-actions').classList.remove('hidden');
    }

    batchState.pageStatuses[pageNum] = status.toLowerCase();
}

// View page results
function viewPageResults(pageNum) {
    // Check if we have a current batch ID
    if (!batchState.currentBatchId) {
        addConsoleMessage('No batch ID available', 'error');
        return;
    }

    // Open modal with page visualization and extracted images
    const modal = document.getElementById('batch-image-modal');
    modal.classList.add('active');

    // Load visualization from the batch report directory
    const vizImage = document.getElementById('modal-visualization-image');
    vizImage.src = `/batch-report-image/${batchState.currentBatchId}/visualization_page_${pageNum}.png?t=${Date.now()}`;

    // Handle loading errors
    vizImage.onerror = function() {
        // Try the regular results directory as fallback
        this.src = `/results/visualization_page_${pageNum}.png?t=${Date.now()}`;

        this.onerror = function() {
            this.alt = 'Visualization not found';
            console.error('Failed to load visualization');
        };
    };

    // Load extracted images
    loadExtractedImagesForPage(pageNum);

    // Update page info
    document.getElementById('modal-page-info').textContent = `Page ${pageNum} Results`;
}

// Load extracted images for a specific page
function loadExtractedImagesForPage(pageNum) {
    const gallery = document.getElementById('modal-extracted-gallery');
    gallery.innerHTML = '<div class="loader"></div> Loading extracted images...';

    // Fetch extracted images for this page
    fetch(`/results/pictures_page_${pageNum}/index.html`)
        .then(response => {
            if (!response.ok) throw new Error('No extracted images');
            return response.text();
        })
        .then(html => {
            // Parse and display images
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const images = doc.querySelectorAll('.picture-card img');

            if (images.length === 0) {
                gallery.innerHTML = '<p class="no-images">No images extracted from this page</p>';
                return;
            }

            let galleryHTML = '';
            images.forEach(img => {
                const src = img.getAttribute('src');
                galleryHTML += `
                    <div class="modal-gallery-item">
                        <img src="/results/pictures_page_${pageNum}/${src}" 
                             alt="Extracted image" 
                             onclick="window.open('/results/pictures_page_${pageNum}/${src}', '_blank')">
                    </div>
                `;
            });

            gallery.innerHTML = galleryHTML;
        })
        .catch(error => {
            gallery.innerHTML = '<p class="no-images">No extracted images available</p>';
        });
}

// Switch modal tabs
function switchModalTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.modal-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    event.target.classList.add('active');

    // Update content
    document.querySelectorAll('.modal-tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`modal-${tabName}-content`).classList.add('active');
}

// Close modal
function closeBatchImageModal() {
    document.getElementById('batch-image-modal').classList.remove('active');
}

// Pause batch processing
function pauseBatchProcessing() {
    if (!batchState.isProcessing || batchState.isPaused) return;

    batchState.isPaused = true;

    fetch(`/pause-batch/${batchState.currentBatchId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addConsoleMessage('Batch processing paused', 'info');
                document.getElementById('pause-batch-btn').classList.add('hidden');
                document.getElementById('resume-batch-btn').classList.remove('hidden');
            }
        })
        .catch(error => {
            console.error('Error pausing batch:', error);
            addConsoleMessage('Error pausing batch: ' + error.message, 'error');
        });
}

// Resume batch processing
function resumeBatchProcessing() {
    if (!batchState.isProcessing || !batchState.isPaused) return;

    batchState.isPaused = false;

    fetch(`/resume-batch/${batchState.currentBatchId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addConsoleMessage('Batch processing resumed', 'info');
                document.getElementById('resume-batch-btn').classList.add('hidden');
                document.getElementById('pause-batch-btn').classList.remove('hidden');

                // Resume polling
                pollBatchStatus();
            }
        })
        .catch(error => {
            console.error('Error resuming batch:', error);
            addConsoleMessage('Error resuming batch: ' + error.message, 'error');
        });
}

// Cancel batch processing
function cancelBatchProcessing() {
    if (!batchState.isProcessing) return;

    if (!confirm('Are you sure you want to cancel the batch processing?')) {
        return;
    }

    fetch(`/cancel-batch/${batchState.currentBatchId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addConsoleMessage('Batch processing cancelled', 'warning');
                finishBatchProcessing(false);
            }
        })
        .catch(error => {
            console.error('Error cancelling batch:', error);
            addConsoleMessage('Error cancelling batch: ' + error.message, 'error');
        });
}

// Finish batch processing
function finishBatchProcessing(success) {
    batchState.isProcessing = false;
    stopElapsedTimer();

    // Update UI
    updateUIForProcessing(false);

    // Show results
    document.getElementById('batch-results').classList.remove('hidden');
    updateResultsSummary();

    if (success) {
        addConsoleMessage('Batch processing completed successfully!', 'success');
    } else {
        addConsoleMessage('Batch processing stopped', 'warning');
    }

    // Update failed pages list if any
    if (batchState.results.failedPages.length > 0) {
        showFailedPages();
    }
}

// Update results summary
function updateResultsSummary() {
    document.getElementById('stat-success').textContent = batchState.results.successful;
    document.getElementById('stat-failed').textContent = batchState.results.failed;
    document.getElementById('stat-duration').textContent = formatTime(Date.now() - batchState.startTime);
    document.getElementById('stat-images').textContent = batchState.results.totalImages;
}

// Show failed pages
function showFailedPages() {
    const failedSection = document.getElementById('failed-pages');
    const failedList = document.getElementById('failed-list');

    failedSection.classList.remove('hidden');
    failedList.innerHTML = '';

    batchState.results.failedPages.forEach(page => {
        const item = document.createElement('div');
        item.className = 'failed-item';
        item.innerHTML = `
            <span>Page ${page.pageNum}</span>
            <span class="failed-reason">${page.reason}</span>
            <button class="retry-btn" onclick="retryPage(${page.pageNum})">Retry</button>
        `;
        failedList.appendChild(item);
    });
}

// Retry failed page
function retryPage(pageNum) {
    addConsoleMessage(`Retrying page ${pageNum}...`, 'info');

    const formData = new FormData();
    formData.append('pdf_file', document.getElementById('batch_pdf_file').value);
    formData.append('page_num', pageNum);
    formData.append('adjust', document.getElementById('batch_adjust').checked);

    // Update page status
    updatePageStatus(pageNum, 'processing');

    fetch('/retry-page', {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updatePageStatus(pageNum, 'completed');
                addConsoleMessage(`Page ${pageNum} processed successfully`, 'success');

                // Update results
                batchState.results.successful++;
                batchState.results.failed--;
                batchState.results.failedPages = batchState.results.failedPages.filter(p => p.pageNum !== pageNum);
                updateResultsSummary();

                if (batchState.results.failedPages.length === 0) {
                    document.getElementById('failed-pages').classList.add('hidden');
                }
            } else {
                updatePageStatus(pageNum, 'failed');
                addConsoleMessage(`Failed to process page ${pageNum}: ${data.error}`, 'error');
            }
        })
        .catch(error => {
            updatePageStatus(pageNum, 'failed');
            addConsoleMessage(`Error retrying page ${pageNum}: ${error.message}`, 'error');
        });
}

// Download all results
function downloadResults() {
    addConsoleMessage('Preparing results for download...', 'info');

    fetch(`/download-batch-results/${batchState.currentBatchId}`)
        .then(response => {
            if (!response.ok) throw new Error('Failed to prepare download');
            return response.blob();
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `doctags_batch_results_${new Date().toISOString().split('T')[0]}.zip`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            addConsoleMessage('Download started', 'success');
        })
        .catch(error => {
            addConsoleMessage('Error downloading results: ' + error.message, 'error');
        });
}

// View detailed report
function viewReport() {
    window.open(`/batch-report/${batchState.currentBatchId}`, '_blank');
}

// Open results folder
function openResultsFolder() {
    addConsoleMessage('Opening results folder...', 'info');

    fetch('/open-results-folder', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addConsoleMessage('Results folder opened', 'success');
            } else {
                addConsoleMessage('Could not open results folder: ' + data.error, 'error');
            }
        })
        .catch(error => {
            addConsoleMessage('Error: ' + error.message, 'error');
        });
}

// Console functions
function addConsoleMessage(message, level = 'info') {
    const console = document.getElementById('console-content');
    const timestamp = new Date().toLocaleTimeString();

    const messageDiv = document.createElement('div');
    messageDiv.className = `console-message ${level}`;
    messageDiv.innerHTML = `<span class="timestamp">[${timestamp}]</span> ${message}`;

    console.appendChild(messageDiv);

    if (batchState.autoScroll) {
        console.scrollTop = console.scrollHeight;
    }
}

function clearConsole() {
    document.getElementById('console-content').innerHTML = '';
}

function toggleAutoScroll() {
    batchState.autoScroll = !batchState.autoScroll;
    document.getElementById('autoscroll-status').textContent =
        `Auto-scroll: ${batchState.autoScroll ? 'ON' : 'OFF'}`;
}

// Timer functions
function startElapsedTimer() {
    elapsedTimer = setInterval(() => {
        const elapsed = Date.now() - batchState.startTime;
        document.getElementById('elapsed-time').textContent = formatTime(elapsed);
    }, 1000);
}

function stopElapsedTimer() {
    if (elapsedTimer) {
        clearInterval(elapsedTimer);
        elapsedTimer = null;
    }
}

// Helper functions
function formatTime(milliseconds) {
    const seconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
        return `${hours}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    } else {
        return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
    }
}

function resetBatchState() {
    batchState.isProcessing = false;
    batchState.isPaused = false;
    batchState.currentBatchId = null;
    batchState.totalPages = 0;
    batchState.processedPages = 0;
    batchState.startTime = null;
    batchState.pageStatuses = {};
    batchState.results = {
        successful: 0,
        failed: 0,
        totalImages: 0,
        failedPages: []
    };
}

function updateUIForProcessing(isProcessing) {
    // Toggle button visibility
    document.getElementById('start-batch-btn').classList.toggle('hidden', isProcessing);
    document.getElementById('pause-batch-btn').classList.toggle('hidden', !isProcessing);
    document.getElementById('cancel-batch-btn').classList.toggle('hidden', !isProcessing);

    // Disable form inputs during processing
    const inputs = document.querySelectorAll('.settings-panel input, .settings-panel select');
    inputs.forEach(input => {
        input.disabled = isProcessing;
    });
}

// Check batch environment
function checkBatchEnvironment() {
    fetch('/check-environment')
        .then(response => response.json())
        .then(data => {
            const envDiv = document.getElementById('batch-environment-check');
            const envDetails = document.getElementById('batch-env-details');

            if (data.missing_scripts.length > 0 || data.pdf_files.length === 0) {
                envDiv.classList.remove('hidden');

                let html = '<ul>';
                if (data.missing_scripts.length > 0) {
                    html += '<li class="env-error">Missing scripts: ' + data.missing_scripts.join(', ') + '</li>';
                }
                if (data.pdf_files.length === 0) {
                    html += '<li class="env-error">No PDF files found in working directory</li>';
                }
                html += '</ul>';

                envDetails.innerHTML = html;
            }
        })
        .catch(error => {
            console.error('Error checking environment:', error);
        });
}