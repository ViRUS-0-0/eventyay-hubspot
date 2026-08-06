document.addEventListener("DOMContentLoaded", function() {
    var container = document.getElementById('mapping-rows');
    var totalFormsInput = document.querySelector('input[name="organizerdefaultobjecttypemapping_set-TOTAL_FORMS"]');
    var addBtn = document.getElementById('add-mapping');
    var PREFIX = 'organizerdefaultobjecttypemapping_set';

    if (!container || !totalFormsInput || !addBtn) return;

    function getEmptyRow(index) {
        var wrapper = document.createElement('div');
        wrapper.className = 'mapping-row';

        var idInput = document.createElement('input');
        idInput.type = 'hidden';
        idInput.name = PREFIX + '-' + index + '-id';
        idInput.id = 'id_' + PREFIX + '-' + index + '-id';
        wrapper.appendChild(idInput);

        var posInput = document.createElement('input');
        posInput.type = 'hidden';
        posInput.name = PREFIX + '-' + index + '-position';
        posInput.id = 'id_' + PREFIX + '-' + index + '-position';
        posInput.className = 'mapping-position';
        posInput.value = '0';
        wrapper.appendChild(posInput);

        var row = document.createElement('div');
        row.className = 'row';

        // eventyay select
        var col1 = document.createElement('div');
        col1.className = 'col-md-4';
        var select1 = document.createElement('select');
        select1.name = PREFIX + '-' + index + '-eventyay_object_type';
        select1.id = 'id_' + PREFIX + '-' + index + '-eventyay_object_type';
        select1.className = 'form-control';
        var ref1 = document.querySelector('select[name$="-eventyay_object_type"]');
        if (ref1) {
            select1.innerHTML = ref1.innerHTML;
            select1.selectedIndex = 0;
        } else {
            select1.innerHTML = '<option value="">---------</option><option value="order">Order</option><option value="order_position">Order position</option>';
        }
        col1.appendChild(select1);
        row.appendChild(col1);

        // hubspot select
        var col2 = document.createElement('div');
        col2.className = 'col-md-4';
        var select2 = document.createElement('select');
        select2.name = PREFIX + '-' + index + '-hubspot_object_type';
        select2.id = 'id_' + PREFIX + '-' + index + '-hubspot_object_type';
        select2.className = 'form-control';
        var ref2 = document.querySelector('select[name$="-hubspot_object_type"]');
        if (ref2) {
            select2.innerHTML = ref2.innerHTML;
            select2.selectedIndex = 0;
        } else {
            select2.innerHTML = '<option value="">---------</option><option value="contacts">Contacts</option><option value="deals">Deals</option>';
        }
        col2.appendChild(select2);
        row.appendChild(col2);

        // action buttons
        var col3 = document.createElement('div');
        col3.className = 'col-md-4';
        var btnGroup = document.createElement('div');
        btnGroup.className = 'btn-group';
        btnGroup.setAttribute('role', 'group');

        var editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'btn btn-default btn-edit-mapping';
        editBtn.disabled = true;
        editBtn.innerHTML = '<i class="fa fa-pencil"></i> ' + (typeof gettext !== 'undefined' ? gettext("Edit mapping") : 'Edit mapping');

        var upBtn = document.createElement('button');
        upBtn.type = 'button';
        upBtn.className = 'btn btn-default btn-move-up';
        upBtn.innerHTML = '<i class="fa fa-arrow-up"></i>';

        var downBtn = document.createElement('button');
        downBtn.type = 'button';
        downBtn.className = 'btn btn-default btn-move-down';
        downBtn.innerHTML = '<i class="fa fa-arrow-down"></i>';

        var deleteInput = document.createElement('input');
        deleteInput.type = 'hidden';
        deleteInput.name = PREFIX + '-' + index + '-DELETE';
        deleteInput.id = 'id_' + PREFIX + '-' + index + '-DELETE';

        var delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'btn btn-danger btn-delete-mapping';
        delBtn.innerHTML = '<i class="fa fa-trash"></i>';

        btnGroup.appendChild(editBtn);
        btnGroup.appendChild(upBtn);
        btnGroup.appendChild(downBtn);
        btnGroup.appendChild(deleteInput);
        btnGroup.appendChild(delBtn);
        col3.appendChild(btnGroup);
        row.appendChild(col3);

        wrapper.appendChild(row);
        return wrapper;
    }

    addBtn.addEventListener('click', function() {
        var currentTotal = parseInt(totalFormsInput.value, 10);
        var newRow = getEmptyRow(currentTotal);
        container.appendChild(newRow);
        totalFormsInput.value = currentTotal + 1;
    });

    container.addEventListener('click', function(e) {
        var target = e.target.closest('button');
        if (!target) return;
        var row = target.closest('.mapping-row');
        if (!row) return;

        if (target.classList.contains('btn-delete-mapping')) {
            var deleteInput = row.querySelector('input[name$="-DELETE"]');
            var idInput = row.querySelector('input[name$="-id"]');
            var isSaved = idInput && idInput.value !== '';

            if (isSaved) {
                // Existing saved row: mark for deletion and hide visually.
                row.classList.add('mapping-row-hidden');
                if (deleteInput) {
                    deleteInput.checked = true;
                    deleteInput.value = 'on';
                }
            } else {
                // Unsaved new row: hide and clear values. Do NOT decrement TOTAL_FORMS,
                // otherwise remaining form indices won't match and data can be dropped.
                row.classList.add('mapping-row-hidden');
                row.querySelectorAll('select').forEach(function(s) {
                    s.value = '';
                });
            }

        } else if (target.classList.contains('btn-move-up')) {
            var prev = row.previousElementSibling;
            if (prev && prev.classList.contains('mapping-row')) {
                container.insertBefore(row, prev);
            }
        } else if (target.classList.contains('btn-move-down')) {
            var next = row.nextElementSibling;
            if (next && next.classList.contains('mapping-row')) {
                container.insertBefore(next, row);
            }
        }
    });

    var form = document.getElementById('mapping-form');
    if (form) {
        form.addEventListener('submit', function() {
            var rows = container.querySelectorAll('.mapping-row');
            var pos = 0;
            rows.forEach(function(row) {
                // Skip hidden/deleted rows — they should not receive a position.
                if (row.classList.contains('mapping-row-hidden')) {
                    return;
                }
                var posInput = row.querySelector('.mapping-position');
                if (posInput) {
                    posInput.value = pos++;
                }
            });
        });
    }

    if (container.querySelectorAll('.mapping-row').length === 0) {
        addBtn.click();
    }
});
