// SomonGame Market - Main JavaScript

// Telegram Web App API
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
}

// Global state
let products = [];
let filteredProducts = [];
let currentGame = '';
let currentCategory = '';

// Initialize app
document.addEventListener('DOMContentLoaded', async () => {
    await loadProducts();
    await loadUserBalance();
    setupEventListeners();
});

// Load products from API
async function loadProducts() {
    try {
        const response = await fetch('/api/products');
        const data = await response.json();
        products = data.products || [];
        filteredProducts = products;
        renderProducts();
        updateCategoryFilter();
    } catch (error) {
        console.error('Error loading products:', error);
        document.getElementById('productsGrid').innerHTML = 
            '<div class="loading">Error loading products. Please try again later.</div>';
    }
}

// Load user balance (mock for now - integrate with Telegram Web App data)
async function loadUserBalance() {
    if (tg && tg.initDataUnsafe?.user) {
        // In production, fetch real balance from API using user ID
        // For now, show placeholder
        document.getElementById('balance').textContent = '$0.00';
    }
}

// Render products grid
function renderProducts() {
    const grid = document.getElementById('productsGrid');
    
    if (filteredProducts.length === 0) {
        grid.innerHTML = '<div class="loading">No products found.</div>';
        return;
    }
    
    grid.innerHTML = filteredProducts.map(product => `
        <div class="product-card" onclick="openProductModal(${product.id})">
            <div class="product-image">
                🎮
            </div>
            <div class="product-info">
                <div class="product-game">${escapeHtml(product.game_type)}</div>
                <div class="product-name">${escapeHtml(product.name)}</div>
                <div class="product-category">${escapeHtml(product.category)}</div>
                <div class="product-price">$${product.price.toFixed(2)}</div>
            </div>
        </div>
    `).join('');
}

// Update category filter options based on selected game
function updateCategoryFilter() {
    const categoryFilter = document.getElementById('categoryFilter');
    const selectedGame = document.getElementById('gameFilter').value;
    
    // Get unique categories for selected game
    const categories = selectedGame
        ? [...new Set(products.filter(p => p.game_type === selectedGame).map(p => p.category))]
        : [...new Set(products.map(p => p.category))];
    
    categoryFilter.innerHTML = '<option value="">All Categories</option>' +
        categories.map(cat => `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}</option>`).join('');
    
    // Reset category filter
    categoryFilter.value = '';
}

// Setup event listeners
function setupEventListeners() {
    // Game filter
    document.getElementById('gameFilter').addEventListener('change', (e) => {
        currentGame = e.target.value;
        filterProducts();
    });
    
    // Category filter
    document.getElementById('categoryFilter').addEventListener('change', (e) => {
        currentCategory = e.target.value;
        filterProducts();
        updateCategoryFilter();
    });
    
    // Modal close
    const modal = document.getElementById('productModal');
    const closeBtn = document.querySelector('.close');
    
    closeBtn?.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    
    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
}

// Filter products
function filterProducts() {
    filteredProducts = products.filter(product => {
        const matchGame = !currentGame || product.game_type === currentGame;
        const matchCategory = !currentCategory || product.category === currentCategory;
        return matchGame && matchCategory;
    });
    renderProducts();
}

// Open product modal
async function openProductModal(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) return;
    
    const modal = document.getElementById('productModal');
    const modalBody = document.getElementById('modalBody');
    
    modalBody.innerHTML = `
        <h2 style="margin-bottom: 1rem; color: var(--neon-purple);">${escapeHtml(product.name)}</h2>
        <div style="margin-bottom: 1rem;">
            <div class="product-game">${escapeHtml(product.game_type)}</div>
            <div class="product-category" style="margin-top: 0.5rem;">${escapeHtml(product.category)}</div>
        </div>
        <div style="margin: 1.5rem 0;">
            <div class="product-price" style="font-size: 2rem;">$${product.price.toFixed(2)}</div>
        </div>
        ${product.description ? `<p style="color: var(--text-secondary); margin: 1rem 0; line-height: 1.8;">${escapeHtml(product.description)}</p>` : ''}
        <button class="btn-primary" onclick="purchaseProduct(${product.id})">
            Buy Now
        </button>
    `;
    
    modal.style.display = 'block';
}

// Purchase product (mock implementation)
function purchaseProduct(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) return;
    
    if (tg) {
        tg.showAlert(`Purchasing ${product.name} for $${product.price.toFixed(2)}...\n\nIn production, this will process the payment.`);
    } else {
        alert(`Purchasing ${product.name} for $${product.price.toFixed(2)}...\n\nIn production, this will process the payment.`);
    }
    
    // Close modal
    document.getElementById('productModal').style.display = 'none';
    
    // In production, make API call to create order
    // await fetch('/api/orders', { method: 'POST', ... });
}

// Utility function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
