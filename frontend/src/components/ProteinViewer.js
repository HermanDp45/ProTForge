import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MdArrowBack, MdContentCopy, MdDownload, MdScience } from 'react-icons/md';

import MolStarViewer from './MolStarViewer';
import ThemeToggle from './ThemeToggle';
import { API_BASE_URL, proteinApi } from '../utils/api';

const hasValue = (value) => value !== undefined && value !== null && value !== '';

const formatMetricValue = (value) => {
  if (!hasValue(value)) {
    return '—';
  }
  if (Array.isArray(value)) {
    return value.join(' × ');
  }
  return value;
};

const wrapSequence = (sequence, width = 60) => {
  const normalized = sequence.replace(/\s+/g, '');
  const lines = [];

  for (let index = 0; index < normalized.length; index += width) {
    lines.push(normalized.slice(index, index + width));
  }

  return lines.join('\n');
};

const sanitizeFastaName = (value) => {
  const name = String(value || 'structure').trim();
  return name.replace(/\s+/g, '_');
};

const buildFasta = (structure) => {
  const sequence = String(structure?.fasta_sequence || '').trim();
  if (!sequence || sequence === 'Sequence unavailable') {
    return '';
  }

  return `>${sanitizeFastaName(structure?.name)}|id=${structure?.id}\n${wrapSequence(sequence)}`;
};

const getMetricCards = (structure) => {
  const metrics = structure?.metrics || {};
  const sequence = String(structure?.fasta_sequence || '').trim();
  const sequenceLength = sequence && sequence !== 'Sequence unavailable' ? sequence.length : null;

  const rows = [
    ['Длина', metrics.length ?? sequenceLength],
    ['Атомы', metrics.atom_count],
    ['Цепи', metrics.chain_count],
    ['Время генерации', metrics.generation_time],
    ['Radius of gyration', metrics.radius_of_gyration],
  ];

  if (Number(metrics.backbone_break_count) > 0) {
    rows.push(['Backbone breaks', metrics.backbone_break_count]);
  }

  rows.push(
    ['CA distance mean', metrics.ca_distance_mean],
    ['CA distance min', metrics.ca_distance_min],
    ['CA distance max', metrics.ca_distance_max],
  );

  return rows.filter(([, value]) => hasValue(value));
};

const getVisibleParams = (params = {}) => {
  const allowedKeys = ['name', 'length', 'source', 'created_at', 'uploaded_at'];
  return allowedKeys.reduce((result, key) => {
    if (hasValue(params[key])) {
      result[key] = params[key];
    }
    return result;
  }, {});
};

const getDetailsTitle = (structure) => (
  structure?.generation_params?.source === 'upload' ? 'Данные загрузки' : 'Параметры генерации'
);

const ProteinViewer = ({ theme, onToggleTheme }) => {
  const { structureId } = useParams();
  const navigate = useNavigate();

  const [structure, setStructure] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copyNotice, setCopyNotice] = useState('');

  useEffect(() => {
    const loadStructure = async () => {
      setLoading(true);
      setError('');
      try {
        const data = await proteinApi.getById(structureId);
        setStructure(data);
      } catch (apiError) {
        setError(apiError.message || 'Не удалось загрузить структуру');
      } finally {
        setLoading(false);
      }
    };

    loadStructure();
  }, [structureId]);

  const pdbUrl = useMemo(() => {
    if (!structure?.pdb_file_path) {
      return '';
    }

    if (structure.pdb_file_path.startsWith('http')) {
      return structure.pdb_file_path;
    }

    return `${API_BASE_URL}${structure.pdb_file_path}`;
  }, [structure]);

  const fastaText = useMemo(() => buildFasta(structure), [structure]);
  const metricCards = useMemo(() => getMetricCards(structure), [structure]);
  const visibleParams = useMemo(() => getVisibleParams(structure?.generation_params), [structure]);

  const handleCopyFasta = async () => {
    if (!fastaText || !navigator?.clipboard) {
      return;
    }

    try {
      await navigator.clipboard.writeText(fastaText);
      setCopyNotice('FASTA скопирована.');
    } catch {
      setCopyNotice('Не удалось скопировать FASTA.');
    }
  };

  const handleDownloadFasta = () => {
    if (!fastaText) {
      return;
    }

    const blob = new Blob([fastaText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${sanitizeFastaName(structure.name)}.fasta`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="screen center">
        <div className="loader" />
        <p>Загрузка структуры...</p>
      </div>
    );
  }

  if (!structure) {
    return (
      <div className="screen center">
        <p>{error || 'Структура не найдена'}</p>
        <button className="btn btn-primary" onClick={() => navigate('/dashboard')}>
          Назад
        </button>
      </div>
    );
  }

  return (
    <div className="screen viewer-screen">
      <header className="app-header animate-in">
        <div className="brand-line">
          <div className="brand-mark small">
            <MdScience />
          </div>
          <div>
            <p className="eyebrow">Structure viewer</p>
            <h1>{structure.name}</h1>
            <p className="muted">Проект #{structure.project_id} · структура #{structure.id}</p>
          </div>
        </div>
        <div className="top-actions">
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          <button className="btn btn-secondary" onClick={() => navigate(`/projects/${structure.project_id}`)}>
            <MdArrowBack />
            К проекту
          </button>
        </div>
      </header>

      {error && <div className="alert alert-error">{error}</div>}
      {copyNotice && <div className="alert alert-success">{copyNotice}</div>}

      <main className="viewer-layout">
        <section className="viewer-main-panel">
          <div className="section-header">
            <h2>3D структура</h2>
            <a className="text-link" href={pdbUrl} target="_blank" rel="noreferrer">
              <MdDownload />
              Открыть PDB
            </a>
          </div>
          <MolStarViewer pdbUrl={pdbUrl} label={structure.name} />
        </section>

        <aside className="viewer-side-panel">
          <section className="compact-panel">
            <h2>Характеристики</h2>
            <div className="metrics-grid">
              {metricCards.map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{formatMetricValue(value)}</strong>
                </div>
              ))}
            </div>
          </section>

          <section className="compact-panel">
            <h2>Источник</h2>
            <div className="metric-list">
              <span>{structure?.generation_params?.source === 'upload' ? 'Загруженный PDB' : 'Сгенерировано в проекте'}</span>
              <span>{structure?.created_at ? new Date(structure.created_at).toLocaleString() : '—'}</span>
            </div>
          </section>
        </aside>
      </main>

      <section className="card">
        <div className="section-header">
          <h2>Последовательность (FASTA)</h2>
          {fastaText && (
            <div className="sequence-actions">
              <button className="btn btn-secondary" type="button" onClick={handleCopyFasta}>
                <MdContentCopy />
                Копировать
              </button>
              <button className="btn btn-secondary" type="button" onClick={handleDownloadFasta}>
                <MdDownload />
                Скачать FASTA
              </button>
            </div>
          )}
        </div>
        <pre className="sequence-box">{fastaText || 'Последовательность не найдена'}</pre>
      </section>

      <section className="card">
        <h2>{getDetailsTitle(structure)}</h2>
        <pre className="sequence-box">{JSON.stringify(visibleParams, null, 2)}</pre>
      </section>
    </div>
  );
};

export default ProteinViewer;
