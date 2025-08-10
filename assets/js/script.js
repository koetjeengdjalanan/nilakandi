Dropzone.autoDiscover = false;

document.addEventListener("DOMContentLoaded", function () {
    // Safe CSRF token acquisition (may be absent on some pages like Operations)
    const csrfTokenInput = document.querySelector("[name=csrfmiddlewaretoken]");
    const csrfToken = csrfTokenInput ? csrfTokenInput.value : null;
    const dropzoneElement = document.querySelector("#byof-dropzone");

    if (dropzoneElement) {
        const submitButton = document.getElementById("byof-submit-button");
        const byofDropZone = new Dropzone("#byof-dropzone", {
            url: dropzoneElement.getAttribute("action"),
            paramName: "file",
            uploadMultiple: true,
            parallelUploads: 6,
            autoProcessQueue: false,
            addRemoveLinks: true,
            maxFilesize: 512, // 512 MB
            timeout: 21600000, // 6 hours
            headers: {
                "x-csrftoken": csrfToken,
            },
            dictDefaultMessage: "Drop files here or click to upload (Max: 512MB per file @ 6 files max)",
            dictFileTooBig: "File is too big ({{filesize}}MB). Max filesize: {{maxFilesize}}MB.",
        });

        byofDropZone.on("successmultiple", function (files, response) {
            if (response.redirect_url) {
                window.location.href = response.redirect_url;
            }
        });

        byofDropZone.on("totaluploadprogress", function (progress) {
            const progressBar = document.getElementById("total-progress-bar");
            if (progressBar) {
                const progressContainer = progressBar.parentElement;
                progressContainer.style.display = "block";
                progressBar.style.width = `${progress}%`;
                progressBar.innerHTML = Math.round(progress) + "%";
            }
        });

        byofDropZone.on("queuecomplete", function () {
            const progressBar = document.getElementById("total-progress-bar");
            if (progressBar) {
                const progressContainer = progressBar.parentElement;
                setTimeout(() => {
                    progressContainer.style.display = "none";
                    progressBar.style.width = "0%";
                    byofDropZone.removeAllFiles();
                }, 2000);
            }
        });

        byofDropZone.on('sendingmultiple', function (file, xhr, formData) {
            const reportTypeElement = document.getElementById('byof_report_type');
            if (reportTypeElement) {
                formData.append('report_type', reportTypeElement.value);
            }
            const subsriptionIdElement = document.getElementById('byof_subscription');
            if (subsriptionIdElement) {
                formData.append('subscription', subsriptionIdElement.value);
            }
            if (submitButton) {
                submitButton.disabled = true;
            }
        });

        if (submitButton) {
            submitButton.addEventListener("click", function () {
                const reportTypeElement = document.getElementById('byof_report_type');
                const subsriptionIdElement = document.getElementById('byof_subscription');
                console.info('Selected params:', reportTypeElement ? reportTypeElement.value : 'None', subsriptionIdElement ? subsriptionIdElement.value : 'None');
                if (!reportTypeElement || !reportTypeElement.value) {
                    alert('Please select a report type before uploading.');
                    return;
                }
                if (!subsriptionIdElement || !subsriptionIdElement.value) {
                    alert('Please select a subscription before uploading.');
                    return;
                }
                byofDropZone.processQueue();
            });
        }
    }

    const byofCard = document.getElementById("byof-card");
    if (byofCard) {
        const tabPanesForHeight = byofCard.querySelectorAll(".tab-content .tab-pane");
        let maxHeight = 0;
        tabPanesForHeight.forEach(function (pane) {
            const height = pane.offsetHeight;
            if (height > maxHeight) {
                maxHeight = height;
            }
        });

        if (maxHeight > 0) {
            const allTabPanes = byofCard.querySelectorAll(".tab-pane");
            allTabPanes.forEach(function (pane) {
                pane.style.height = maxHeight + "px";
            });
        }
        byofCard.addEventListener('keyup', function (event) {
            if (event.target.id === 'search-blob') {
                const searchTerm = event.target.value.toLowerCase();
                const accordions = byofCard.querySelectorAll('#blob-selection .accordion');

                accordions.forEach(accordion => {
                    const files = accordion.querySelectorAll('.form-check');
                    let accordionHasVisibleFiles = false;

                    files.forEach(file => {
                        const label = file.querySelector('label');
                        if (label && label.textContent.toLowerCase().includes(searchTerm)) {
                            file.style.display = '';
                            accordionHasVisibleFiles = true;
                        } else {
                            file.style.display = 'none';
                        }
                    });

                    if (accordionHasVisibleFiles) {
                        accordion.style.display = '';
                    } else {
                        accordion.style.display = 'none';
                    }
                });
            }
        });
    }

    const toastElement = document.querySelector(".toast");
    if (toastElement) {
        const toast = new bootstrap.Toast(toastElement, {
            autohide: true,
            delay: 5000,
        });
        toast.show();
    }

});

// Operations modal handler (kept outside main DOMContentLoaded block so earlier errors don't block it)
document.addEventListener('DOMContentLoaded', function () {
    const tbody = document.querySelector('table.table-hover tbody');
    if (!tbody) { return; }

    function isModalMarkup(html) {
        // Look for id or class to be more resilient to class list changes
        return /id=["']operation-detail-modal["']/.test(html) || /class=["'][^"']*operation-modal/.test(html);
    }

    function injectAndShowModal(html, fallbackUrl, row) {
        const root = document.getElementById('operation-modal-root');
        if (!root) { window.location = fallbackUrl; return; }
        root.innerHTML = html;
        // Accept either id or class selectors
        const modalEl = root.querySelector('#operation-detail-modal') || root.querySelector('.operation-modal');
        if (!modalEl) { window.location = fallbackUrl; return; }
        if (typeof bootstrap === 'undefined' || !bootstrap.Modal) { window.location = fallbackUrl; return; }
        try {
            const instance = bootstrap.Modal.getOrCreateInstance(modalEl, { backdrop: 'static' });
            modalEl.addEventListener('hidden.bs.modal', () => { root.innerHTML = ''; });
            instance.show();
        } catch (e) {
            console.error('Modal init failed, navigating instead', e);
            window.location = fallbackUrl;
        } finally {
            if (row) row.classList.remove('table-active');
        }
    }

    tbody.addEventListener('click', function (evt) {
        const row = evt.target.closest('tr.operation-row');
        if (!row) { return; }
        const detailUrl = row.getAttribute('data-detail-url');
        if (!detailUrl) { return; }
        row.classList.add('table-active');
        fetch(detailUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(resp => {
                // If server responded with redirect (status 302/301), fallback
                if (!resp.ok) {
                    throw new Error('HTTP ' + resp.status);
                }
                return resp.text();
            })
            .then(html => {
                if (isModalMarkup(html)) {
                    injectAndShowModal(html, detailUrl, row);
                } else {
                    window.location = detailUrl;
                }
            })
            .catch(err => {
                console.error('Failed to load operation details', err);
                window.location = detailUrl;
            })
            .finally(() => {
                // If modal path executed, row class removed in inject; else ensure remove here.
                row.classList.remove('table-active');
            });
    });
});