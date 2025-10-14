from typing import List, Dict


class BlockSection:
    def __init__(self, blocks: List[Dict], is_single_task: bool = False):
        self.blocks = blocks
        self.is_single_task = is_single_task


class Sectionizer:
    def segment(self, blocks: List[Dict]) -> List[BlockSection]:
        """Split block tree into sections for single/multi-task inference."""
        import time
        t0 = time.perf_counter()
        try:
            from flask import current_app
            logger = current_app.extensions['app_context'].get_service('app_logger')
        except Exception:
            logger = None

        sections: List[BlockSection] = []
        current_section: List[Dict] = []

        for block in blocks:
            if block.get('type') in ['heading_1', 'heading_2', 'heading_3']:
                if current_section:
                    sections.append(BlockSection(current_section))
                sections.append(BlockSection([block]))
                current_section = []
            else:
                current_section.append(block)

        if current_section:
            sections.append(BlockSection(current_section))

        is_single = len(sections) <= 2 and not any(b.get('type') == 'to_do' for s in sections for b in s.blocks)
        for section in sections:
            section.is_single_task = is_single

        if logger:
            logger.debug(
                "SECTIONIZER.done",
                sections_count=len(sections),
                is_single_task=is_single,
                block_counts=[len(s.blocks) for s in sections],
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )
        return sections


