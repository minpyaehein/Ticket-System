(() => {
    "use strict";

    const searchInput = document.getElementById("permissionSearch");
    const rowsContainer = document.getElementById("permissionRows");
    const visibleCount = document.getElementById("visibleCount");
    const countLabel = document.getElementById("permissionCount");
    const emptyState = document.getElementById("emptyState");

    if (!searchInput || !rowsContainer || !visibleCount || !countLabel || !emptyState) {
        return;
    }

    const rows = Array.from(rowsContainer.querySelectorAll("tr:not(.empty-row)"));
    const total = rows.length;

    function filterPermissionRows() {
        const query = searchInput.value.trim().toLocaleLowerCase();
        let shown = 0;

        rows.forEach((row) => {
            const matches = row.textContent.toLocaleLowerCase().includes(query);
            row.hidden = !matches;
            if (matches) shown += 1;
        });

        emptyState.hidden = shown !== 0;
        visibleCount.textContent = String(shown);
        countLabel.textContent = `${shown} of ${total} modules`;
    }

    searchInput.addEventListener("input", filterPermissionRows);

    // Ctrl+K / Cmd+K focuses the module search without adding dependencies.
    document.addEventListener("keydown", (event) => {
        const isSearchShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
        if (isSearchShortcut) {
            event.preventDefault();
            searchInput.focus();
            searchInput.select();
        }
    });

    filterPermissionRows();
})();
