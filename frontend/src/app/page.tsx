/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.05.28      kimzion77   최초 생성
 * 2026.10.01      이시영      임금명세서·노무제공자 계약서·관리자 기능 삭제
 * 2026.10.06      이시영      PostgreSQL 전환, 노무가이드 삭제
 * 2026.10.06      이시영      API 경로 표준화 (/api/cgr)
 * 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
 * 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
 *
 * Author: kimzion77
 * Since: 2026.05.28
 */
// 개발표준정의서 API 엔드포인트(화면 경로): basePath /cgr 의 첫 화면 — 업로드 화면 본문은 HomeScreen 으로 분리 (기존: 이 파일에 직접 구현)
import HomeScreen from '@/components/home/HomeScreen';

/** 서비스 첫 화면 — 문서 종류 선택 + 업로드. */
export default function HomePage() {
  return <HomeScreen />;
}
