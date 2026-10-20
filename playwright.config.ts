import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests/ui',use:{baseURL:'http://127.0.0.1:8000',trace:'retain-on-failure'},projects:[{name:'desktop',use:{viewport:{width:1440,height:1000}}},{name:'mobile',use:{viewport:{width:390,height:844}}}]});
