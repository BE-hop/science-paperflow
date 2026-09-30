document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      const textarea = document.querySelector("#agent-prompt");
      if (textarea) {
        textarea.value = button.dataset.prompt;
        textarea.focus();
      }
    });
  });

  const jobCard = document.querySelector("[data-job-id]");
  if (jobCard && jobCard.dataset.terminal !== "true") {
    const source = new EventSource(`/jobs/${jobCard.dataset.jobId}/events`);
    source.onmessage = (event) => {
      const job = JSON.parse(event.data);
      document.querySelector("#job-status").textContent = job.status;
      document.querySelector("#job-title").textContent = job.summary;
      if (["completed", "needs_user", "failed", "cancelled", "applied"].includes(job.status)) {
        source.close();
        window.setTimeout(() => window.location.reload(), 500);
      }
    };
  }
});
