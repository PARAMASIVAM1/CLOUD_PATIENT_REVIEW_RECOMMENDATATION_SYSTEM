@echo off
del /f /q "d:\syllabus2026\SEAP PROJECT\pgsql\data\postmaster.pid" 2>nul
"d:\syllabus2026\SEAP PROJECT\pgsql\bin\postgres.exe" -D "d:\syllabus2026\SEAP PROJECT\pgsql\data"

