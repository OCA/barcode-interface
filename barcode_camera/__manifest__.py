{
    "name": "Barcode Camera",
    "version": "18.0.1.0.0",
    "category": "Hidden",
    "summary": "Scan barcodes with the device camera in the Barcode app",
    "author": "Binhex, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/barcode-interface",
    "maintainers": ["szalatyzuzanna"],
    "license": "AGPL-3",
    "depends": [
        "barcode_scanner",
    ],
    "assets": {
        "barcode_scanner.assets": [
            "barcode_camera/static/src/components/**/*.esm.js",
            "barcode_camera/static/src/components/**/*.xml",
            "barcode_camera/static/src/components/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "barcode_camera/static/tests/**/*",
        ],
    },
    "installable": True,
    "auto_install": False,
}
