document.addEventListener('DOMContentLoaded', function() {
    var selectAll = document.getElementById('select-all');
    var checkboxes = document.getElementsByClassName('log-checkbox');
    var deleteBtn = document.getElementById('delete-logs-btn');

    function updateDeleteBtn() {
        var anyChecked = false;
        for (var i = 0; i < checkboxes.length; i++) {
            if (checkboxes[i].checked) {
                anyChecked = true;
                break;
            }
        }
        deleteBtn.style.display = anyChecked ? 'inline-block' : 'none';
    }

    if (selectAll) {
        selectAll.addEventListener('change', function() {
            for (var i = 0; i < checkboxes.length; i++) {
                checkboxes[i].checked = this.checked;
            }
            updateDeleteBtn();
            
            var selectAllMsg = document.getElementById('select-all-message');
            var allSelectedMsg = document.getElementById('all-pages-selected-message');
            var selectAllInput = document.getElementById('select-all-pages-input');
            
            if (selectAllMsg) {
                if (this.checked) {
                    selectAllMsg.style.display = 'block';
                    allSelectedMsg.style.display = 'none';
                    selectAllInput.value = '0';
                } else {
                    selectAllMsg.style.display = 'none';
                    allSelectedMsg.style.display = 'none';
                    selectAllInput.value = '0';
                }
            }
        });
    }

    var selectAllPagesLink = document.getElementById('select-all-pages-link');
    var clearSelectionLink = document.getElementById('clear-selection-link');
    var selectAllMsg = document.getElementById('select-all-message');
    var allSelectedMsg = document.getElementById('all-pages-selected-message');
    var selectAllInput = document.getElementById('select-all-pages-input');

    if (selectAllPagesLink) {
        selectAllPagesLink.addEventListener('click', function(e) {
            e.preventDefault();
            selectAllMsg.style.display = 'none';
            allSelectedMsg.style.display = 'block';
            selectAllInput.value = '1';
        });
    }

    if (clearSelectionLink) {
        clearSelectionLink.addEventListener('click', function(e) {
            e.preventDefault();
            selectAll.checked = false;
            for (var i = 0; i < checkboxes.length; i++) {
                checkboxes[i].checked = false;
            }
            selectAllMsg.style.display = 'none';
            allSelectedMsg.style.display = 'none';
            selectAllInput.value = '0';
            updateDeleteBtn();
        });
    }

    for (var i = 0; i < checkboxes.length; i++) {
        checkboxes[i].addEventListener('change', function() {
            updateDeleteBtn();
            if (!this.checked && selectAll.checked) {
                selectAll.checked = false;
                if (selectAllMsg) {
                    selectAllMsg.style.display = 'none';
                    allSelectedMsg.style.display = 'none';
                    selectAllInput.value = '0';
                }
            }
        });
    }
});
