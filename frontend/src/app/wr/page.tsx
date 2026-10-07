/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.10.07      이시영      최초 생성
 * 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
 *
 * Author: 이시영
 * Since: 2026.10.07
 */
// 프로그램명세서 WR-001-01 취업규칙 제출: 화면 URL /cgr/wr (신규 — 기존: / 에서 문서 종류 선택)
import HomeScreen from '@/components/home/HomeScreen';

/** 취업규칙 업로드. */
export default function WrUploadPage() {
  return <HomeScreen initialDocType="work-rules" />;
}
