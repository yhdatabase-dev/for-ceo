'use client';

import { useMemo } from 'react';

import type {
  EcStructuredData,
  EcStructuredField,
} from '@/lib/api/types';

import styles from './EditableStructureTable.module.css';

interface EditableStructureTableProps {
  /** 백엔드 `/ec/structure` 가 돌려준 8섹션 dict. */
  value: EcStructuredData;
  /** 사용자가 행 단위로 value/note 를 수정할 때 호출. */
  onChange: (next: EcStructuredData) => void;
}

function isFieldMap(v: unknown): v is Record<string, EcStructuredField> {
  return (
    typeof v === 'object' &&
    v !== null &&
    !Array.isArray(v) &&
    Object.values(v).every(
      (x) =>
        x !== null &&
        typeof x === 'object' &&
        'value' in (x as Record<string, unknown>) &&
        'note' in (x as Record<string, unknown>),
    )
  );
}

/**
 * 8섹션 구조화 데이터 표 — 사용자가 OCR 결과를 검토·수정하는 UI.
 *
 * 기존 `1. 근로계약서/기존/src/EditableStructureTable.jsx` 를 그대로 옮겨와
 * Next.js (TS + CSS Modules) 컨벤션에 맞춰 재작성.
 *
 * - 각 섹션은 카드 + 표(항목/내용/비고)로 렌더
 * - 마지막 `기타사항` 배열은 별도 카드에 bullet 목록으로 표시 (읽기 전용 — OCR 잔여)
 */
export function EditableStructureTable({
  value,
  onChange,
}: EditableStructureTableProps) {
  const sections = useMemo(() => {
    return Object.entries(value).filter(([k]) => k !== '기타사항');
  }, [value]);

  const updateField = (
    section: string,
    fieldName: string,
    key: 'value' | 'note',
    next: string,
  ) => {
    const sec = value[section];
    if (!isFieldMap(sec)) return;
    const updated: EcStructuredData = {
      ...value,
      [section]: {
        ...sec,
        [fieldName]: { ...sec[fieldName], [key]: next },
      },
    };
    onChange(updated);
  };

  const extras = Array.isArray(value['기타사항'])
    ? (value['기타사항'] as string[])
    : [];

  return (
    <div className={styles.wrap}>
      {sections.map(([sectionName, sectionData]) => {
        if (!isFieldMap(sectionData)) return null;
        const rows = Object.entries(sectionData);
        return (
          <section key={sectionName} className={styles.section}>
            <header className={styles.sectionHead}>
              <h3 className={styles.sectionTitle}>{sectionName}</h3>
            </header>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.colKey}>항목</th>
                  <th className={styles.colValue}>내용</th>
                  <th className={styles.colNote}>비고</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([fieldName, field]) => (
                  <tr key={fieldName}>
                    <td className={styles.cellKey}>{fieldName}</td>
                    <td className={styles.cellInput}>
                      <input
                        type="text"
                        className={styles.input}
                        value={field.value}
                        onChange={(e) =>
                          updateField(
                            sectionName,
                            fieldName,
                            'value',
                            e.target.value,
                          )
                        }
                        placeholder="미기재"
                      />
                    </td>
                    <td className={styles.cellInput}>
                      <input
                        type="text"
                        className={`${styles.input} ${styles.inputNote}`}
                        value={field.note}
                        onChange={(e) =>
                          updateField(
                            sectionName,
                            fieldName,
                            'note',
                            e.target.value,
                          )
                        }
                        placeholder="비고사항"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        );
      })}

      {extras.length > 0 && (
        <section className={styles.section}>
          <header className={styles.sectionHead}>
            <h3 className={styles.sectionTitle}>기타사항</h3>
          </header>
          <ul className={styles.extras}>
            {extras.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export default EditableStructureTable;
