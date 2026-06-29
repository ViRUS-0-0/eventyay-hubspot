document.addEventListener("DOMContentLoaded", function() {
    var logsContainer = document.getElementById("logs-container");
    var filterDropdown = document.getElementById("filterDropdown");
    var filterDropdownContainer = document.getElementById("filterDropdownContainer");
    
    function loadLogs(url) {
        logsContainer.style.opacity = '0.5';
        fetch(url, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.text())
        .then(html => {
            var parser = new DOMParser();
            var doc = parser.parseFromString(html, 'text/html');
            var newLogsContainer = doc.getElementById('logs-container');
            if (newLogsContainer) {
                logsContainer.innerHTML = newLogsContainer.innerHTML;
            }
            logsContainer.style.opacity = '1';
            
            // Also update the dropdown text if it's a filter click
            let searchParams = new URL(url, window.location.origin).searchParams;
            let type = searchParams.get('type');
            let filterText = filterDropdownContainer.dataset.allActivity;
            if (type === 'sync') {
                filterText = filterDropdownContainer.dataset.syncActivity;
            } else if (type === 'settings') {
                filterText = filterDropdownContainer.dataset.settingsChanges;
            }
            filterDropdown.innerHTML = filterText + ' <span class="caret"></span>';
            
            // Update URL in browser history
            window.history.pushState({path: url}, '', url);
        });
    }
    
    document.body.addEventListener('click', function(e) {
        // Handle dropdown links
        var dropdownLink = e.target.closest('.dropdown-menu a');
        if (dropdownLink) {
            e.preventDefault();
            loadLogs(dropdownLink.href);
            return;
        }
        
        // Handle pagination links
        var paginationLink = e.target.closest('.pagination a');
        if (paginationLink && logsContainer.contains(paginationLink)) {
            e.preventDefault();
            loadLogs(paginationLink.href);
            return;
        }
    });
    
    window.addEventListener('popstate', function(e) {
        if(e.state && e.state.path) {
            loadLogs(e.state.path);
        }
    });
});
