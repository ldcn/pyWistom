// Global variables and utility functions for the network monitoring app

// Configuration
const CONFIG = {
    autoRefreshInterval: 10000, // 10 seconds
    connectionTimeout: 5000,    // 5 seconds
    maxRetries: 3
};

// Utility functions
const Utils = {
    formatBytes: function(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    
    formatUptime: function(seconds) {
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        
        let result = '';
        if (days > 0) result += days + 'd ';
        if (hours > 0) result += hours + 'h ';
        if (minutes > 0) result += minutes + 'm';
        
        return result || '< 1m';
    },
    
    isValidIP: function(ip) {
        const regex = /^(\d{1,3}\.){3}\d{1,3}$/;
        if (!regex.test(ip)) return false;
        
        return ip.split('.').every(octet => {
            const num = parseInt(octet);
            return num >= 0 && num <= 255;
        });
    },
    
    isValidMAC: function(mac) {
        const regex = /^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/;
        return regex.test(mac);
    },
    
    copyToClipboard: function(text) {
        return navigator.clipboard.writeText(text);
    },
    
    showNotification: function(message, type = 'info') {
        // Simple notification system
        const notification = $(`
            <div class="notification notification-${type}">
                ${message}
                <button class="notification-close">&times;</button>
            </div>
        `);
        
        $('body').append(notification);
        
        // Auto-hide after 3 seconds
        setTimeout(() => {
            notification.fadeOut(() => notification.remove());
        }, 3000);
        
        // Manual close
        notification.find('.notification-close').click(() => {
            notification.fadeOut(() => notification.remove());
        });
    }
};

// Network status checker
const NetworkChecker = {
    pingEndpoint: function(url) {
        const startTime = Date.now();
        
        return $.ajax({
            url: url,
            method: 'GET',
            timeout: CONFIG.connectionTimeout
        }).then(
            () => Date.now() - startTime,
            () => -1
        );
    },
    
    checkConnectivity: async function() {
        const results = await Promise.all([
            this.pingEndpoint('/network_info'),
            this.pingEndpoint('/api/system_info')
        ]);
        
        const avgResponseTime = results.filter(r => r > 0).reduce((a, b) => a + b, 0) / results.filter(r => r > 0).length;
        const successRate = results.filter(r => r > 0).length / results.length;
        
        return {
            responseTime: avgResponseTime || -1,
            successRate: successRate,
            status: successRate > 0.5 ? 'connected' : 'disconnected'
        };
    }
};

// Data validator
const DataValidator = {
    validateNetworkData: function(data) {
        const errors = [];
        const warnings = [];
        
        if (data.ip_address && !Utils.isValidIP(data.ip_address)) {
            errors.push('Invalid IP address format');
        }
        
        if (data.gateway && !Utils.isValidIP(data.gateway)) {
            warnings.push('Gateway IP address format looks suspicious');
        }
        
        if (data.mac_address && !Utils.isValidMAC(data.mac_address)) {
            warnings.push('MAC address format looks unusual');
        }
        
        if (data.ip_address && data.gateway) {
            // Check if gateway is in same subnet (basic check)
            const ipParts = data.ip_address.split('.');
            const gatewayParts = data.gateway.split('.');
            
            if (ipParts[0] !== gatewayParts[0] || ipParts[1] !== gatewayParts[1]) {
                warnings.push('Gateway might not be in the same subnet');
            }
        }
        
        return { errors, warnings };
    }
};

// Export for use in other files
window.Utils = Utils;
window.NetworkChecker = NetworkChecker;
window.DataValidator = DataValidator;
window.CONFIG = CONFIG;