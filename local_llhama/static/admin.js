// Admin Panel JavaScript

let currentEditingUser = null;

// Load users on page load
document.addEventListener('DOMContentLoaded', () => {
    loadUsers();
});

async function loadUsers() {
    try {
        const response = await fetch('/admin/users');
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        displayUsers(data.users);
    } catch (error) {
        showError('Failed to load users: ' + error.message);
    }
}

function displayUsers(users) {
    const tbody = document.getElementById('users-table-body');
    
    if (users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 20px;">No users found</td></tr>';
        return;
    }
    
    tbody.innerHTML = users.map(user => `
        <tr>
            <td><strong>${escapeHtml(user.username)}</strong></td>
            <td>
                ${user.is_active ? '<span class="permission-badge badge-yes">Active</span>' : '<span class="permission-badge badge-no">Inactive</span>'}
                ${user.must_change_password ? '<span class="permission-badge badge-warning">Must Change Password</span>' : ''}
            </td>
            <td>
                ${user.is_admin ? '<span class="permission-badge badge-admin">Admin</span>' : ''}
                ${user.can_access_dashboard ? '<span class="permission-badge badge-yes">Dashboard</span>' : '<span class="permission-badge badge-no">No Dashboard</span>'}
                ${user.can_access_chat ? '<span class="permission-badge badge-yes">Chat</span>' : '<span class="permission-badge badge-no">No Chat</span>'}
            </td>
            <td>${formatDate(user.created_at)}</td>
            <td>${user.last_login ? formatDate(user.last_login) : 'Never'}</td>
            <td>
                <div class="action-buttons">
                    <button class="btn-small btn-edit" onclick="editPermissions('${escapeHtml(user.username)}', ${JSON.stringify(user).replace(/"/g, '&quot;')})">Edit</button>
                    <button class="btn-small btn-reset" onclick="resetPassword('${escapeHtml(user.username)}')">Reset Password</button>
                    ${user.username !== 'admin' ? `<button class="btn-small btn-delete" onclick="deleteUser('${escapeHtml(user.username)}')">Delete</button>` : ''}
                </div>
            </td>
        </tr>
    `).join('');
}

function showCreateUserModal() {
    document.getElementById('createUserModal').style.display = 'block';
    document.getElementById('createUserForm').reset();
    document.getElementById('newPasswordDisplay').style.display = 'none';
}

function editPermissions(username, userData) {
    currentEditingUser = username;
    document.getElementById('editUsername').textContent = username;
    document.getElementById('editIsAdmin').checked = userData.is_admin;
    document.getElementById('editCanDashboard').checked = userData.can_access_dashboard;
    document.getElementById('editCanChat').checked = userData.can_access_chat;
    document.getElementById('editIsActive').checked = userData.is_active;
    document.getElementById('editPermissionsModal').style.display = 'block';
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Close modal when clicking outside
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
}

// Create User Form Handler
document.getElementById('createUserForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const username = document.getElementById('newUsername').value.trim();
    const isAdmin = document.getElementById('newIsAdmin').checked;
    const canDashboard = document.getElementById('newCanDashboard').checked;
    const canChat = document.getElementById('newCanChat').checked;
    
    try {
        const response = await fetch('/admin/users', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                username: username,
                is_admin: isAdmin,
                can_access_dashboard: canDashboard,
                can_access_chat: canChat
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        if (data.success) {
            // Show generated password
            document.getElementById('newPasswordDisplay').innerHTML = `
                <div class="password-display">
                    <h3>⚠️ User Created Successfully</h3>
                    <p>Username: <strong>${escapeHtml(data.username)}</strong></p>
                    <p>Temporary Password:</p>
                    <div class="password-value">${escapeHtml(data.password)}</div>
                    <p class="password-warning">${data.warning}</p>
                </div>
            `;
            document.getElementById('newPasswordDisplay').style.display = 'block';
            
            // Hide form
            document.getElementById('createUserForm').style.display = 'none';
            
            // Reload users list
            loadUsers();
        }
    } catch (error) {
        showError('Failed to create user: ' + error.message);
    }
});

// Edit Permissions Form Handler
document.getElementById('editPermissionsForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!currentEditingUser) return;
    
    const isAdmin = document.getElementById('editIsAdmin').checked;
    const canDashboard = document.getElementById('editCanDashboard').checked;
    const canChat = document.getElementById('editCanChat').checked;
    const isActive = document.getElementById('editIsActive').checked;
    
    try {
        const response = await fetch(`/admin/users/${currentEditingUser}/permissions`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                is_admin: isAdmin,
                can_access_dashboard: canDashboard,
                can_access_chat: canChat,
                is_active: isActive
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        if (data.success) {
            closeModal('editPermissionsModal');
            loadUsers();
            showSuccess('Permissions updated successfully');
        }
    } catch (error) {
        showError('Failed to update permissions: ' + error.message);
    }
});

async function resetPassword(username) {
    if (!confirm(`Reset password for user "${username}"? A new temporary password will be generated.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/admin/users/${username}/password`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        if (data.success) {
            // Show new password in modal
            document.getElementById('resetPasswordDisplay').innerHTML = `
                <div class="password-display">
                    <h3>⚠️ Password Reset Successfully</h3>
                    <p>Username: <strong>${escapeHtml(data.username)}</strong></p>
                    <p>New Temporary Password:</p>
                    <div class="password-value">${escapeHtml(data.password)}</div>
                    <p class="password-warning">${data.warning}</p>
                    <p class="password-warning">User will be required to change this password on next login.</p>
                </div>
            `;
            document.getElementById('resetPasswordModal').style.display = 'block';
            loadUsers();
        }
    } catch (error) {
        showError('Failed to reset password: ' + error.message);
    }
}

async function deleteUser(username) {
    if (!confirm(`Are you sure you want to delete user "${username}"? This action cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/admin/users/${username}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        if (data.success) {
            loadUsers();
            showSuccess('User deleted successfully');
        }
    } catch (error) {
        showError('Failed to delete user: ' + error.message);
    }
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showError(message) {
    alert('Error: ' + message);
}

function showSuccess(message) {
    alert(message);
}
