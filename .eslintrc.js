export default {
    "env": {
        "browser": true,
        "es2021": true
    },
    "extends": [
        "eslint:recommended",
        "plugin:vue/essential"
    ],
    "parserOptions": {
        "ecmaVersion": "latest",
        "sourceType": "module",
    },
    "plugins": [
        "vue"
    ],
    "rules": {
    },
    "globals": {
        "_": true,
        "Cookies": true,
        "Fuse": true,
        "filterXSS": true,
        "machina": true,
        "moment": true,
        "objectHash": true,
        "renderjson": true,
        "showdown": true,
        "SVG": true,
        "Tabulator": true,
        "URI": true,
        "vis": true
    }
}
