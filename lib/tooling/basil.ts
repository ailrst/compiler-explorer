// Copyright (c) 2023, Compiler Explorer Authors
// All rights reserved.
//
// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided that the following conditions are met:
//
//     * Redistributions of source code must retain the above copyright notice,
//       this list of conditions and the following disclaimer.
//     * Redistributions in binary form must reproduce the above copyright
//       notice, this list of conditions and the following disclaimer in the
//       documentation and/or other materials provided with the distribution.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
// AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
// IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
// ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
// LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
// CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
// SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
// INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
// CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
// ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
// POSSIBILITY OF SUCH DAMAGE.

import fs from 'fs-extra';

import {logger} from '../logger.js';
import {BaseTool} from './base-tool.js';
import {ExecutionOptions} from '../../types/compilation/compilation.interfaces.js';

export class BasilTool extends BaseTool {
    static get key() {
        return 'basil-tool';
    }

    override getDefaultExecOptions(): ExecutionOptions {
        logger.info('Using execoptions');
        return {
            timeoutMs: this.env.ceProps('compileTimeoutMs', 300000) as number,
            maxErrorOutput: this.env.ceProps('max-error-output', 5000) as number,
            wrapper: this.env.compilerProps('compiler-wrapper'),
        };
    }

    override async runTool(compilationInfo: Record<any, any>, inputFilepath?: string, args?: string[]) {
        if (!compilationInfo.filters.binary && !compilationInfo.filters.binaryObject) {
            return this.createErrorResponse(`${this.tool.name ?? 'tool'} requires an executable or binary object`);
        }
        args = args || [];
        args.push('-d');
        args.push(compilationInfo.dirPath);
        logger.info(compilationInfo);
        logger.info(args);

        if (await fs.pathExists(compilationInfo.executableFilename)) {
            return super.runTool(compilationInfo, compilationInfo.executableFilename, args);
        }
        return super.runTool(compilationInfo, compilationInfo.outputFilename, args);
    }
}
