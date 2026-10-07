// 프로그램명세서 WR-001-01 취업규칙 제출: 화면 URL /cgr/wr (신규 — 기존: / 에서 문서 종류 선택)
import HomeScreen from '@/components/home/HomeScreen';

/** 취업규칙 업로드. */
export default function WrUploadPage() {
  return <HomeScreen initialDocType="work-rules" />;
}
