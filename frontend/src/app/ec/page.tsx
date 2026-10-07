// 프로그램명세서 LC-001-01 근로계약서 업로드: 화면 URL /cgr/ec (신규 — 기존: / 에서 문서 종류 선택)
import HomeScreen from '@/components/home/HomeScreen';

/** 근로계약서 업로드. */
export default function EcUploadPage() {
  return <HomeScreen initialDocType="employment-contract" />;
}
