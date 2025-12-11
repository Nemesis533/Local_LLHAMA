/**
 * User Management Module
 * Handles user CRUD operations, permissions, and password management
 */

import { escapeHtml, formatDate, showError, showSuccess, closeModal } from './utils.js';

let currentEditingUser = null;

/**
 * Load and display users
 */
export async function loadUsers() {
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

/**
 * Display users in table
 */
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
                ${user.can_access_chat ? '<span class="permission-badge badge-yes">Chat</span>' : '<span class="permission-badge badge-no">No Chat</span>'}
            </td>
            <td>${formatDate(user.created_at)}</td>
            <td>${user.last_login ? formatDate(user.last_login) : 'Never'}</td>
            <td>
                <div class="action-buttons">
                    <button class="btn-small btn-edit" onclick="window.userManagement.editPermissions('${escapeHtml(user.username)}', ${JSON.stringify(user).replace(/"/g, '&quot;')})">Edit</button>
                    <button class="btn-small btn-reset" onclick="window.userManagement.resetPassword('${escapeHtml(user.username)}')">Reset Password</button>
                    ${user.username !== 'admin' ? `<button class="btn-small btn-delete" onclick="window.userManagement.deleteUser('${escapeHtml(user.username)}')">Delete</button>` : ''}
                </div>
            </td>
        </tr>
    `).join('');
}

/**
 * Show create user modal
 */
export function showCreateUserModal() {
    document.getElementById('createUserModal').style.display = 'block';
    document.getElementById('createUserForm').reset();
    document.getElementById('newPasswordDisplay').style.display = 'none';
    document.getElementById('createUserForm').style.display = 'block';
}

/**
 * Edit user permissions
 */
export function editPermissions(username, userData) {
    currentEditingUser = username;
    document.getElementById('editUsername').textContent = username;
    document.getElementById('editIsAdmin').checked = userData.is_admin;
    document.getElementById('editCanChat').checked = userData.can_access_chat;
    document.getElementById('editIsActive').checked = userData.is_active;
    document.getElementById('editPermissionsModal').style.display = 'block';
}

/**
 * Create new user
 */
export async function createUser(username, isAdmin, canChat) {
    try {
        const response = await fetch('/admin/users', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                username: username,
                is_admin: isAdmin,
                can_access_chat: canChat
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return null;
        }
        
        if (data.success) {
            loadUsers();
            return data;
        }
    } catch (error) {
        showError('Failed to create user: ' + error.message);
        return null;
    }
}

/**
 * Update user permissions
 */
export async function updatePermissions(username, isAdmin, canChat, isActive) {
    try {
        const response = await fetch(`/admin/users/${username}/permissions`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                is_admin: isAdmin,
                can_access_chat: canChat,
                is_active: isActive
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return false;
        }
        
        if (data.success) {
            loadUsers();
            return true;
        }
    } catch (error) {
        showError('Failed to update permissions: ' + error.message);
        return false;
    }
}

/**
 * Reset user password
 */
export async function resetPassword(username) {
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
                    <h3>Password Reset Successfully</h3>
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

/**
 * Delete user
 */
export async function deleteUser(username) {
    if (!confirm(`Are you sure you want to delete user "${username}"?\n\nThis will permanently delete:\n- The user account\n- All conversations and chat history\n\nThis action cannot be undone.`)) {
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

/**
 * Initialize user management event listeners
 */
export function initUserManagement() {
    // Create User Form Handler
    document.getElementById('createUserForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('newUsername').value.trim();
        const isAdmin = document.getElementById('newIsAdmin').checked;
        const canChat = document.getElementById('newCanChat').checked;
        
        const data = await createUser(username, isAdmin, canChat);
        
        if (data && data.success) {
            // Show generated password
            document.getElementById('newPasswordDisplay').innerHTML = `
                <div class="password-display">
                    <h3>User Created Successfully</h3>
                    <p>Username: <strong>${escapeHtml(data.username)}</strong></p>
                    <p>Temporary Password:</p>
                    <div class="password-value">${escapeHtml(data.password)}</div>
                    <p class="password-warning">${data.warning}</p>
                </div>
            `;
            document.getElementById('newPasswordDisplay').style.display = 'block';
            document.getElementById('createUserForm').style.display = 'none';
        }
    });

    // Edit Permissions Form Handler
    document.getElementById('editPermissionsForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        if (!currentEditingUser) return;
        
        const isAdmin = document.getElementById('editIsAdmin').checked;
        const canChat = document.getElementById('editCanChat').checked;
        const isActive = document.getElementById('editIsActive').checked;
        
        const success = await updatePermissions(currentEditingUser, isAdmin, canChat, isActive);
        
        if (success) {
            closeModal('editPermissionsModal');
            showSuccess('Permissions updated successfully');
        }
    });
}
