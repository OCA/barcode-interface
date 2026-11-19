{
    "name": "Barcode Purchase",
    "version": "18.0.1.0.0",
    "category": "Inventory/Purchase",
    "summary": "Create purchase orders by barcode: scan products against a "
    "vendor and confirm the order from the scanner",
    "author": "Binhex, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/barcode-interface",
    "maintainers": ["szalatyzuzanna"],
    "license": "AGPL-3",
    "depends": [
        "barcode_scanner",
        "purchase_stock",
    ],
    "data": [
        "views/purchase_order_views.xml",
    ],
    "assets": {
        "barcode_scanner.assets": [
            "barcode_purchase/static/src/**/*.esm.js",
            "barcode_purchase/static/src/**/*.xml",
            "barcode_purchase/static/src/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "barcode_purchase/static/tests/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
