"""core — 앱 전역에 한 번 설치되는 것 (config, database, logging, exceptions, security).

판정 기준: 앱 기동 시 한 번 설치되거나, 모든 계층이 import 하는가.
도메인 이름이 들어간 파일이 생기면 잘못 들어온 것.
"""
