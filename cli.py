import argparse
import os
import sys

import pandas as pd

from utils.logger import get_logger
from utils.config import load_config, get_config_value, merge_cli_overrides
from data_loader import load_and_copy_testset
from model_tester import run_model, save_outputs
from evaluator import evaluate


logger = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='自动化测试AI模型工具')
    sub = p.add_subparsers(dest='command', required=True)

    def common_args(sp: argparse.ArgumentParser):
        sp.add_argument('--config', type=str, default='config.ini', help='配置文件路径(默认: config.ini)')
        sp.add_argument('--dataset', type=str, help='测试集文件路径(Excel/CSV)')
        sp.add_argument('--model-endpoint', type=str, help='被测模型API端点')
        sp.add_argument('--model-api-key', type=str, help='模型API密钥')
        sp.add_argument('--input-field', type=str, default=None, help='模型请求输入字段名(默认: input)')
        sp.add_argument('--model-timeout', type=int, default=None, help='模型API超时(秒)')
        sp.add_argument('--model-retries', type=int, default=None, help='模型API重试次数')
        sp.add_argument('--model-kind', type=str, default=None, choices=['generic', 'dify_completion', 'dify_chat'], help='模型API类型')
        sp.add_argument('--judge-endpoint', type=str, help='裁判工作流API端点')
        sp.add_argument('--judge-api-key', type=str, help='裁判API密钥')
        sp.add_argument('--batch-size', type=int, default=None, help='裁判批量处理大小(默认: 1)')
        sp.add_argument('--max-merge-rows', type=int, default=None, help='裁判多行合并最大行数(默认: 1)')
        sp.add_argument('--judge-timeout', type=int, default=None, help='裁判API超时(秒)')
        sp.add_argument('--judge-retries', type=int, default=None, help='裁判API重试次数')
        sp.add_argument('--judge-kind', type=str, default=None, choices=['dify_workflow', 'generic'], help='裁判API类型')
        sp.add_argument('--user-id', type=str, default=None, help='Dify user字段(默认: auto-ai-testing)')

    # test 命令
    sp_test = sub.add_parser('test', help='仅执行模型测试并生成输出文件')
    common_args(sp_test)

    # evaluate 命令
    sp_eval = sub.add_parser('evaluate', help='仅对已有输出文件进行裁判评估')
    common_args(sp_eval)
    sp_eval.add_argument('--input', type=str, help='模型输出文件路径(.csv或.xlsx)')

    # run 命令
    sp_run = sub.add_parser('run', help='先测试模型再进行裁判评估')
    common_args(sp_run)

    return p


def _load_paths(cfg):
    test_sets_dir = get_config_value(cfg, 'paths', 'test_sets_dir', 'test_sets')
    output_results_dir = get_config_value(cfg, 'paths', 'output_results_dir', 'output_results')
    evaluation_results_dir = get_config_value(cfg, 'paths', 'evaluation_results_dir', 'evaluation_results')
    return test_sets_dir, output_results_dir, evaluation_results_dir


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = load_config(args.config)

    test_sets_dir, output_results_dir, evaluation_results_dir = _load_paths(cfg)

    base_conf = {
        'model_endpoint': get_config_value(cfg, 'model_api', 'endpoint', None),
        'model_api_key': get_config_value(cfg, 'model_api', 'api_key', None),
        'input_field': get_config_value(cfg, 'model_api', 'input_field', 'input'),
        'model_timeout': int(get_config_value(cfg, 'model_api', 'timeout', '30')),
        'model_retries': int(get_config_value(cfg, 'model_api', 'retries', '3')),
        'model_kind': get_config_value(cfg, 'model_api', 'kind', 'generic'),
        'judge_endpoint': get_config_value(cfg, 'judge_api', 'endpoint', None),
        'judge_api_key': get_config_value(cfg, 'judge_api', 'api_key', None),
        'batch_size': int(get_config_value(cfg, 'judge_api', 'batch_size', '1')),
        'max_merge_rows': int(get_config_value(cfg, 'judge_api', 'max_merge_rows', '1')),
        'judge_timeout': int(get_config_value(cfg, 'judge_api', 'timeout', '30')),
        'judge_retries': int(get_config_value(cfg, 'judge_api', 'retries', '3')),
        'judge_kind': get_config_value(cfg, 'judge_api', 'kind', 'dify_workflow'),
        'dataset': get_config_value(cfg, 'execution', 'dataset', None),
        'user_id': get_config_value(cfg, 'execution', 'user', 'auto-ai-testing'),
    }

    overrides = {
        'model_endpoint': args.model_endpoint,
        'model_api_key': args.model_api_key,
        'input_field': args.input_field,
        'model_timeout': args.model_timeout,
        'model_retries': args.model_retries,
        'model_kind': args.model_kind,
        'judge_endpoint': args.judge_endpoint,
        'judge_api_key': args.judge_api_key,
        'batch_size': args.batch_size,
        'max_merge_rows': args.max_merge_rows,
        'judge_timeout': args.judge_timeout,
        'judge_retries': args.judge_retries,
        'judge_kind': args.judge_kind,
        'dataset': args.dataset,
        'user_id': args.user_id,
    }

    conf = merge_cli_overrides(base_conf, overrides)

    cmd = args.command
    if cmd == 'test' or cmd == 'run':
        if not conf['dataset']:
            logger.error('未提供测试集路径，请使用 --dataset 或在配置文件execution.dataset中设置')
            return 2
        copied_path, df, base_name = load_and_copy_testset(conf['dataset'], test_sets_dir)
        # 模型测试
        logger.info('开始模型测试...')
        results = run_model(
            df,
            endpoint=conf['model_endpoint'],
            api_key=conf['model_api_key'],
            input_field=conf['input_field'] or 'input',
            timeout=conf['model_timeout'],
            retries=conf['model_retries'],
            model_kind=conf['model_kind'],
            user_id=conf['user_id'],
        )
        out_path, ftype = save_outputs(results, copied_path, output_results_dir, base_name)
        logger.info(f'模型测试完成，输出文件: {out_path}')
        if cmd == 'test':
            return 0
        # 继续评估
        logger.info('开始裁判评估...')
        eval_df, eval_path = evaluate(
            results,
            copied_dataset_path=copied_path,
            endpoint=conf['judge_endpoint'],
            api_key=conf['judge_api_key'],
            batch_size=conf['batch_size'],
            max_merge_rows=conf['max_merge_rows'],
            timeout=conf['judge_timeout'],
            retries=conf['judge_retries'],
            base_name=base_name,
            judge_kind=conf['judge_kind'],
            user_id=conf['user_id'],
            evaluation_results_dir=evaluation_results_dir,
        )
        logger.info(f'裁判评估完成，评估文件: {eval_path}')
        return 0

    if cmd == 'evaluate':
        # 仅评估：从 --input 指定的文件载入
        if not args.input:
            logger.error('evaluate需要 --input 指定模型输出文件(.csv/.xlsx)')
            return 2
        path = args.input
        if not os.path.exists(path):
            logger.error(f'输入文件不存在: {path}')
            return 2
        logger.info(f'加载输出文件用于评估: {path}')
        ext = os.path.splitext(path)[1].lower()
        if ext == '.csv':
            df = pd.read_csv(path, encoding='utf-8')
        else:
            df = pd.read_excel(path)
        # 需要原复制文件路径以判断类型，这里用输入文件替代即可
        base_name = os.path.splitext(os.path.basename(path))[0]
        eval_df, eval_path = evaluate(
            df,
            copied_dataset_path=path,
            endpoint=conf['judge_endpoint'],
            api_key=conf['judge_api_key'],
            batch_size=conf['batch_size'],
            max_merge_rows=conf['max_merge_rows'],
            timeout=conf['judge_timeout'],
            retries=conf['judge_retries'],
            base_name=base_name,
            judge_kind=conf['judge_kind'],
            user_id=conf['user_id'],
            evaluation_results_dir=evaluation_results_dir,
        )
        logger.info(f'裁判评估完成，评估文件: {eval_path}')
        return 0

    return 0


if __name__ == '__main__':
    sys.exit(main())