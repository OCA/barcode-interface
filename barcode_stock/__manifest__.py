{
    "name": "Barcode Stock",
    "version": "18.0.1.0.5",
    "category": "Inventory/Logistics",
    "summary": "Warehouse operations (receipts, deliveries, internal transfers) "
    "for the Barcode suite",
    "author": "Binhex, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/barcode-interface",
    "maintainers": ["szalatyzuzanna"],
    "license": "AGPL-3",
    "depends": [
        "barcode_scanner",
        "barcodes",
        "stock",
        "stock_move_line_qty_picked",
    ],
    "data": [
        "views/stock_location_views.xml",
    ],
    "assets": {
        "barcode_scanner.assets": [
            "barcode_stock/static/src/**/*.esm.js",
            "barcode_stock/static/src/**/*.xml",
            "barcode_stock/static/src/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "barcode_stock/static/tests/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
