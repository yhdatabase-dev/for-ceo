// 개발표준정의서 API 엔드포인트(화면 경로): basePath /cgr 의 첫 화면 — 업로드 화면 본문은 HomeScreen 으로 분리 (기존: 이 파일에 직접 구현)
import HomeScreen from '@/components/home/HomeScreen';

/** 서비스 첫 화면 — 문서 종류 선택 + 업로드. */
export default function HomePage() {
  return <HomeScreen />;
}
