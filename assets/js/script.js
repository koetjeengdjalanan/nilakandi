Dropzone.autoDiscover = false;

document.addEventListener("DOMContentLoaded", function () {
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]").value;
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
            maxFilesize: 512,
            timeout: 900000,
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
});