import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MdArrowBack, MdDelete, MdSave, MdScience, MdUploadFile, MdVisibility } from 'react-icons/md';

import ThemeToggle from './ThemeToggle';
import { projectApi, proteinApi } from '../utils/api';

const hasMetricValue = (value) => value !== undefined && value !== null && value !== '';

const metricValue = (value) => {
  if (!hasMetricValue(value)) {
    return '—';
  }
  if (Array.isArray(value)) {
    return value.join(' × ');
  }
  return value;
};

const getCaDistanceSummary = (metrics) => {
  const mean = metrics.ca_distance_mean;
  const min = metrics.ca_distance_min;
  const max = metrics.ca_distance_max;

  if (hasMetricValue(mean) && hasMetricValue(min) && hasMetricValue(max)) {
    return `${mean} Å (${min}-${max})`;
  }

  if (hasMetricValue(mean)) {
    return mean;
  }

  return null;
};

const getStructureMetrics = (structure) => {
  const metrics = structure?.metrics || {};
  const sequence = String(structure?.fasta_sequence || '').trim();
  const sequenceLength = sequence && sequence !== 'Sequence unavailable' ? sequence.length : null;
  const caDistanceSummary = getCaDistanceSummary(metrics);
  const rows = [
    ['Длина', metrics.length ?? sequenceLength],
    ['Атомы', metrics.atom_count],
    ['Цепи', metrics.chain_count],
    ['Время', metrics.generation_time],
    ['Rg', metrics.radius_of_gyration],
  ];

  if (Number(metrics.backbone_break_count) > 0) {
    rows.push(['Backbone breaks', metrics.backbone_break_count]);
  }

  if (caDistanceSummary) {
    rows.push(['CA distance', caDistanceSummary]);
  }

  return rows.filter(([, value]) => hasMetricValue(value));
};

const ProjectPage = ({ theme, onToggleTheme }) => {
  const { projectId } = useParams();
  const navigate = useNavigate();

  const [project, setProject] = useState(null);
  const [structures, setStructures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('structures');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [savingProject, setSavingProject] = useState(false);
  const [projectForm, setProjectForm] = useState({
    name: '',
    description: '',
  });

  const [generating, setGenerating] = useState(false);
  const [generationForm, setGenerationForm] = useState({
    name: '',
    length: 160,
  });

  const [uploading, setUploading] = useState(false);
  const [uploadName, setUploadName] = useState('');
  const [uploadFile, setUploadFile] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [projectData, structuresData] = await Promise.all([
        projectApi.getById(projectId),
        proteinApi.getByProject(projectId),
      ]);
      setProject(projectData);
      setStructures(Array.isArray(structuresData) ? structuresData : []);
      setProjectForm({
        name: projectData.name || '',
        description: projectData.description || '',
      });
    } catch (apiError) {
      setError(apiError.message || 'Не удалось загрузить проект');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSaveProject = async (event) => {
    event.preventDefault();
    if (!projectForm.name.trim()) {
      return;
    }

    setSavingProject(true);
    setError('');
    setNotice('');
    try {
      const updated = await projectApi.update(projectId, {
        name: projectForm.name.trim(),
        description: projectForm.description.trim(),
      });
      setProject(updated);
      setNotice('Проект сохранен.');
    } catch (apiError) {
      setError(apiError.message || 'Не удалось сохранить проект');
    } finally {
      setSavingProject(false);
    }
  };

  const handleGenerate = async (event) => {
    event.preventDefault();
    setGenerating(true);
    setError('');
    setNotice('');
    try {
      const payload = {
        name: generationForm.name.trim(),
        length: Number(generationForm.length),
      };

      const response = await proteinApi.generate(projectId, payload, true);
      if (response.status === 'queued') {
        setNotice('Генерация запущена. Обнови список через некоторое время.');
      } else {
        setNotice('Структура сгенерирована.');
      }
      await loadData();
      setTab('structures');
    } catch (apiError) {
      setError(apiError.message || 'Ошибка генерации белка');
    } finally {
      setGenerating(false);
    }
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!uploadFile || !uploadName.trim()) {
      setError('Укажи имя структуры и выбери .pdb файл');
      setNotice('');
      return;
    }

    setUploading(true);
    setError('');
    setNotice('');
    try {
      await proteinApi.upload(projectId, uploadFile, uploadName.trim());
      setUploadName('');
      setUploadFile(null);
      const fileInput = document.getElementById('upload-input');
      if (fileInput) {
        fileInput.value = '';
      }
      await loadData();
      setTab('structures');
      setNotice('PDB-структура загружена и добавлена в проект.');
    } catch (apiError) {
      setError(apiError.message || 'Ошибка загрузки структуры');
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteStructure = async (structureId) => {
    const shouldDelete = window.confirm('Удалить структуру?');
    if (!shouldDelete) {
      return;
    }

    try {
      await proteinApi.delete(structureId);
      setStructures((prev) => prev.filter((structure) => structure.id !== structureId));
      setNotice('Структура удалена.');
    } catch (apiError) {
      setError(apiError.message || 'Не удалось удалить структуру');
    }
  };

  if (loading) {
    return (
      <div className="screen center">
        <div className="loader" />
        <p>Загрузка проекта...</p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="screen center">
        <p>Проект не найден.</p>
        <button className="btn btn-primary" onClick={() => navigate('/dashboard')}>
          Назад
        </button>
      </div>
    );
  }

  return (
    <div className="screen project-screen">
      <header className="app-header animate-in">
        <div>
          <p className="eyebrow">Project workspace</p>
          <h1>{project.name}</h1>
          <p className="muted">Проект #{project.id}</p>
        </div>
        <div className="top-actions">
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          <button className="btn btn-secondary" onClick={() => navigate('/dashboard')}>
            <MdArrowBack />
            К проектам
          </button>
        </div>
      </header>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-success">{notice}</div>}

      <section className="hero-panel animate-in delay-1">
        <div>
          <p className="eyebrow">Design board</p>
          <h2>Генерация, загрузка и анализ структур</h2>
          <p className="muted">Сначала задай описание проекта, затем переходи к структурам или параметрам генерации.</p>
        </div>
        <div className="hero-actions">
          <button className="btn btn-primary" onClick={() => setTab('generate')}>
            <MdScience />
            Генерация
          </button>
          <button className="btn btn-secondary" onClick={() => setTab('upload')}>
            <MdUploadFile />
            Загрузить PDB
          </button>
        </div>
      </section>

      <section className="card animate-in delay-2">
        <div className="section-header">
          <h2>Параметры проекта</h2>
          <button className="btn btn-primary" type="submit" form="project-form" disabled={savingProject}>
            <MdSave />
            {savingProject ? 'Сохраняем...' : 'Сохранить'}
          </button>
        </div>
        <form id="project-form" className="form-grid" onSubmit={handleSaveProject}>
          <label>
            Название
            <input
              type="text"
              value={projectForm.name}
              onChange={(event) => setProjectForm((prev) => ({ ...prev, name: event.target.value }))}
              maxLength={100}
              required
            />
          </label>
          <label>
            Описание
            <textarea
              rows={4}
              value={projectForm.description}
              onChange={(event) => setProjectForm((prev) => ({ ...prev, description: event.target.value }))}
              maxLength={2000}
            />
          </label>
        </form>
      </section>

      <div className="tabs-row animate-in delay-3">
        <button className={`tab-btn ${tab === 'structures' ? 'active' : ''}`} onClick={() => setTab('structures')}>
          <MdVisibility />
          Структуры
        </button>
        <button className={`tab-btn ${tab === 'generate' ? 'active' : ''}`} onClick={() => setTab('generate')}>
          <MdScience />
          Генерация
        </button>
        <button className={`tab-btn ${tab === 'upload' ? 'active' : ''}`} onClick={() => setTab('upload')}>
          <MdUploadFile />
          Загрузка PDB
        </button>
      </div>

      {tab === 'structures' && (
        <section className="card animate-in">
          <div className="section-header">
            <h2>Структуры белков</h2>
            <button className="btn btn-secondary" onClick={loadData}>
              Обновить список
            </button>
          </div>

          {structures.length === 0 ? (
            <p className="muted">В проекте пока нет структур.</p>
          ) : (
            <div className="project-grid">
              {structures.map((structure) => (
                <article key={structure.id} className="project-card">
                  <h3>{structure.name}</h3>
                  <p className="muted small">Создано: {new Date(structure.created_at).toLocaleString()}</p>
                  <p className="muted small">
                    Источник: {structure?.generation_params?.source === 'upload' ? 'Загрузка' : 'Генерация'}
                  </p>

                  <div className="metric-list">
                    {getStructureMetrics(structure).map(([label, value]) => (
                      <span key={label}>{label}: {metricValue(value)}</span>
                    ))}
                  </div>

                  <div className="actions-row">
                    <button className="btn btn-primary" onClick={() => navigate(`/proteins/${structure.id}`)}>
                      <MdVisibility />
                      3D просмотр
                    </button>
                    <button className="icon-btn danger" onClick={() => handleDeleteStructure(structure.id)} title="Удалить структуру">
                      <MdDelete />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {tab === 'generate' && (
        <section className="card animate-in">
          <h2>Генерация белка</h2>
          <form className="form-grid" onSubmit={handleGenerate}>
            <label>
              Название структуры
              <input
                type="text"
                value={generationForm.name}
                onChange={(event) => setGenerationForm((prev) => ({ ...prev, name: event.target.value }))}
                maxLength={100}
                placeholder="Например: DiMA helix 160"
              />
            </label>

            <label>
              Длина последовательности (50-254)
              <input
                type="number"
                min={50}
                max={254}
                value={generationForm.length}
                onChange={(event) => setGenerationForm((prev) => ({ ...prev, length: event.target.value }))}
                required
              />
            </label>

            <button className="btn btn-primary" type="submit" disabled={generating}>
              <MdScience />
              {generating ? 'Генерируем...' : 'Запустить генерацию'}
            </button>
          </form>
        </section>
      )}

      {tab === 'upload' && (
        <section className="card animate-in">
          <h2>Загрузка готовой структуры</h2>
          <form className="form-grid" onSubmit={handleUpload}>
            <label>
              Название структуры
              <input
                type="text"
                value={uploadName}
                onChange={(event) => setUploadName(event.target.value)}
                maxLength={100}
                required
              />
            </label>

            <label>
              Файл PDB
              <input
                id="upload-input"
                type="file"
                accept=".pdb"
                onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
                required
              />
            </label>

            <button className="btn btn-primary" type="submit" disabled={uploading}>
              <MdUploadFile />
              {uploading ? 'Загружаем...' : 'Загрузить структуру'}
            </button>
          </form>
        </section>
      )}
    </div>
  );
};

export default ProjectPage;
